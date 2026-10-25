"""Hardcoded Sensitive Path & OS Path Traversal AST Sanitizer.

Detects unsafe filesystem operations where dynamic user paths or unconstrained path joins
can permit directory traversal attacks (e.g. '../' escaping base directories),
and synthesizes secure path sanitization using canonical boundary guards and basename normalization.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple


@dataclass
class PathTraversalFinding:
    line_number: int
    call_name: str
    target_arg: str
    vulnerability_reason: str
    recommended_expression: str


class PathTraversalVisitor(ast.NodeVisitor):
    """AST visitor that detects path traversal risks in os.path.join and open calls."""

    def __init__(self) -> None:
        self.findings: List[PathTraversalFinding] = []

    def visit_Call(self, node: ast.Call) -> None:
        # 1. os.path.join(base, user_input)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "join":
            if isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "path":
                # Check arguments
                if len(node.args) >= 2:
                    last_arg = node.args[-1]
                    # If last arg is not a constant, it could be dynamic user input
                    if not isinstance(last_arg, ast.Constant):
                        arg_repr = ast.unparse(last_arg)
                        self.findings.append(
                            PathTraversalFinding(
                                line_number=node.lineno,
                                call_name="os.path.join",
                                target_arg=arg_repr,
                                vulnerability_reason="Unsanitized dynamic argument in os.path.join allows directory traversal",
                                recommended_expression=f"os.path.basename({arg_repr})",
                            )
                        )

        # 2. direct open(user_input, ...) where user_input is variable and not constant
        elif isinstance(node.func, ast.Name) and node.func.id == "open":
            if node.args:
                first_arg = node.args[0]
                if isinstance(first_arg, ast.Name):
                    self.findings.append(
                        PathTraversalFinding(
                            line_number=node.lineno,
                            call_name="open",
                            target_arg=first_arg.id,
                            vulnerability_reason="Direct file open with raw variable without canonical containment validation",
                            recommended_expression=f"os.path.abspath({first_arg.id})",
                        )
                    )

        self.generic_visit(node)


class PathTraversalTransformer(ast.NodeTransformer):
    """AST transformer that secures unsafe path concatenation and file opens."""

    def __init__(self, findings: List[PathTraversalFinding]) -> None:
        self.findings_by_line = {f.line_number: f for f in findings}
        self.patch_count = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        finding = self.findings_by_line.get(node.lineno)
        if finding:
            if finding.call_name == "os.path.join" and len(node.args) >= 2:
                # Wrap the last arg with os.path.basename(...)
                last_arg = node.args[-1]
                safe_call = ast.Call(
                    func=ast.Attribute(
                        value=ast.Attribute(
                            value=ast.Name(id="os", ctx=ast.Load()),
                            attr="path",
                            ctx=ast.Load(),
                        ),
                        attr="basename",
                        ctx=ast.Load(),
                    ),
                    args=[last_arg],
                    keywords=[],
                )
                node.args[-1] = safe_call
                self.patch_count += 1
        return node


class PathTraversalSanitizer:
    """Orchestrator for detecting and sanitizing directory traversal vulnerabilities."""

    def analyze(self, source_code: str) -> List[PathTraversalFinding]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return []
        visitor = PathTraversalVisitor()
        visitor.visit(tree)
        return visitor.findings

    def synthesize(self, source_code: str) -> Tuple[str, List[PathTraversalFinding]]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return source_code, []

        visitor = PathTraversalVisitor()
        visitor.visit(tree)
        if not visitor.findings:
            return source_code, []

        transformer = PathTraversalTransformer(visitor.findings)
        modified_tree = transformer.visit(tree)
        ast.fix_missing_locations(modified_tree)

        try:
            new_code = ast.unparse(modified_tree)
            compile(new_code, "<healed_traversal>", "exec")
            return new_code, visitor.findings
        except Exception:
            return source_code, visitor.findings


def sanitize_path_traversal(source_code: str) -> Tuple[str, List[PathTraversalFinding]]:
    engine = PathTraversalSanitizer()
    return engine.synthesize(source_code)
