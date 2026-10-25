"""Unhandled Exception & Fault Boundary Synthesizer.

Detects unguarded, fault-prone expressions and calls (e.g. json.loads,
requests, int/float parsing, math domains) and automatically synthesizes
resilient try-except fallback boundaries while preserving program semantics.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class ExceptionBoundaryFinding:
    function_name: Optional[str]
    call_name: str
    line_number: int
    exception_type: str
    suggested_fallback: str


DEFAULT_RISKY_PATTERNS: Dict[str, Tuple[str, str]] = {
    # Call pattern -> (Exception type, Default fallback expression)
    "json.loads": ("json.JSONDecodeError", "{}"),
    "json.load": ("json.JSONDecodeError", "{}"),
    "requests.get": ("requests.RequestException", "None"),
    "requests.post": ("requests.RequestException", "None"),
    "urllib.request.urlopen": ("OSError", "None"),
    "int": ("ValueError", "0"),
    "float": ("ValueError", "0.0"),
    "math.sqrt": ("ValueError", "0.0"),
}


class _TryBlockAnalyzer(ast.NodeVisitor):
    """Tracks exception handlers covering statements."""

    def __init__(self) -> None:
        self.try_covered_lines: Dict[int, Set[str]] = {}

    def visit_Try(self, node: ast.Try) -> None:
        handled_exceptions: Set[str] = set()
        for handler in node.handlers:
            if handler.type is None:
                handled_exceptions.add("Exception")
                handled_exceptions.add("BaseException")
            elif isinstance(handler.type, ast.Name):
                handled_exceptions.add(handler.type.id)
            elif isinstance(handler.type, ast.Attribute):
                handled_exceptions.add(handler.type.attr)
                # e.g. json.JSONDecodeError -> JSONDecodeError
                handled_exceptions.add(f"{ast.unparse(handler.type)}")

        # Mark all lines in body as covered by these exceptions
        for child in node.body:
            for n in ast.walk(child):
                if hasattr(n, "lineno"):
                    if n.lineno not in self.try_covered_lines:
                        self.try_covered_lines[n.lineno] = set()
                    self.try_covered_lines[n.lineno].update(handled_exceptions)

        self.generic_visit(node)


class ExceptionBoundarySynthesizer(ast.NodeTransformer):
    """Detects unguarded calls and synthesizes protective try-except blocks."""

    def __init__(self, custom_rules: Optional[Dict[str, Tuple[str, str]]] = None) -> None:
        super().__init__()
        self.rules = custom_rules or DEFAULT_RISKY_PATTERNS
        self.findings: List[ExceptionBoundaryFinding] = []
        self._current_function: Optional[str] = None
        self._try_analyzer = _TryBlockAnalyzer()

    def scan(self, tree: ast.AST) -> List[ExceptionBoundaryFinding]:
        """Scans AST for unguarded fault-prone calls without modifying."""
        self._try_analyzer = _TryBlockAnalyzer()
        self._try_analyzer.visit(tree)
        findings: List[ExceptionBoundaryFinding] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                fn_name = node.name
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Call):
                        finding = self._inspect_call(inner, fn_name)
                        if finding:
                            findings.append(finding)

        return findings

    def _inspect_call(self, call_node: ast.Call, fn_name: Optional[str]) -> Optional[ExceptionBoundaryFinding]:
        call_str = ast.unparse(call_node.func)
        matched_pattern = None

        for pattern, (exc_type, fallback) in self.rules.items():
            if call_str == pattern or call_str.endswith(f".{pattern}"):
                matched_pattern = (pattern, exc_type, fallback)
                break

        if not matched_pattern:
            return None

        pattern, exc_type, fallback = matched_pattern
        lineno = getattr(call_node, "lineno", 0)

        # Check if lineno is covered in a try block handling this exception
        covered = self._try_analyzer.try_covered_lines.get(lineno, set())
        if exc_type in covered or "Exception" in covered or "BaseException" in covered:
            return None

        return ExceptionBoundaryFinding(
            function_name=fn_name,
            call_name=call_str,
            line_number=lineno,
            exception_type=exc_type,
            suggested_fallback=fallback,
        )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        old_fn = self._current_function
        self._current_function = node.name
        node.body = self._wrap_body_statements(node.body)
        self._current_function = old_fn
        return self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        old_fn = self._current_function
        self._current_function = node.name
        node.body = self._wrap_body_statements(node.body)
        self._current_function = old_fn
        return self.generic_visit(node)

    def _wrap_body_statements(self, statements: List[ast.stmt]) -> List[ast.stmt]:
        new_statements: List[ast.stmt] = []

        for stmt in statements:
            # If the statement is an assignment with an unguarded risky call:
            # e.g., data = json.loads(payload)
            # Transform into:
            # try:
            #     data = json.loads(payload)
            # except JSONDecodeError:
            #     data = {}
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.value, ast.Call):
                call_finding = self._inspect_call(stmt.value, self._current_function)
                if call_finding:
                    self.findings.append(call_finding)
                    target = stmt.targets[0]
                    fallback_node = ast.parse(call_finding.suggested_fallback, mode="eval").body

                    try_stmt = ast.Try(
                        body=[stmt],
                        handlers=[
                            ast.ExceptHandler(
                                type=ast.parse(call_finding.exception_type, mode="eval").body,
                                name=None,
                                body=[ast.Assign(targets=[target], value=fallback_node)],
                            )
                        ],
                        orelse=[],
                        finalbody=[],
                    )
                    ast.copy_location(try_stmt, stmt)
                    new_statements.append(try_stmt)
                    continue

            new_statements.append(stmt)

        return new_statements


def synthesize_exception_boundaries(
    source_code: str,
    custom_rules: Optional[Dict[str, Tuple[str, str]]] = None,
) -> Tuple[str, List[ExceptionBoundaryFinding]]:
    """Inspects and rewrites source code to wrap unguarded calls in try-except blocks."""
    tree = ast.parse(source_code)
    synthesizer = ExceptionBoundarySynthesizer(custom_rules)
    # First scan for initial analysis
    synthesizer.scan(tree)
    # Then transform
    transformed = synthesizer.visit(tree)
    ast.fix_missing_locations(transformed)

    new_source = ast.unparse(transformed)
    # Validate syntax by parsing and compiling
    compiled = compile(new_source, "<synthesized_fault_boundary>", mode="exec")
    return new_source, synthesizer.findings
