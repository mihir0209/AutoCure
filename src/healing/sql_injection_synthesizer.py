"""SQL Injection Vulnerability Heuristic & Parameterized Query Synthesizer.

Detects insecure SQL query construction (f-strings, % formatting, .format(), string concatenation)
passed to database execute calls (e.g. cursor.execute, db.execute, session.execute),
and automatically synthesizes secure parameterized queries with parameter tuple binding.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple


@dataclass
class SQLInjectionFinding:
    line_number: int
    vulnerability_type: str  # "f-string", "percent_format", "str_format", "concat"
    original_call: str
    recommended_query: str
    extracted_params: List[str]


class SQLInjectionVisitor(ast.NodeVisitor):
    """Detects SQL execute calls with unsafe string formatting."""

    EXECUTE_METHODS = {"execute", "executemany", "raw", "raw_sql", "execute_sql"}

    def __init__(self) -> None:
        self.findings: List[SQLInjectionFinding] = []

    def visit_Call(self, node: ast.Call) -> None:
        method_name = ""
        if isinstance(node.func, ast.Attribute) and node.func.attr in self.EXECUTE_METHODS:
            method_name = node.func.attr
        elif isinstance(node.func, ast.Name) and node.func.id in self.EXECUTE_METHODS:
            method_name = node.func.id

        if method_name and node.args:
            first_arg = node.args[0]
            finding = self._inspect_sql_argument(first_arg)
            if finding:
                finding.original_call = ast.unparse(node)
                self.findings.append(finding)

        self.generic_visit(node)

    def _inspect_sql_argument(self, arg: ast.AST) -> Optional[SQLInjectionFinding]:
        # 1. f-string: ast.JoinedStr
        if isinstance(arg, ast.JoinedStr):
            parts = []
            params = []
            for val in arg.values:
                if isinstance(val, ast.Constant) and isinstance(val.value, str):
                    parts.append(val.value)
                elif isinstance(val, ast.FormattedValue):
                    parts.append("%s")
                    params.append(ast.unparse(val.value))
            template = "".join(parts)
            return SQLInjectionFinding(
                line_number=arg.lineno,
                vulnerability_type="f-string",
                original_call="",
                recommended_query=template,
                extracted_params=params,
            )

        # 2. Modulo string formatting: "SELECT ... %s" % (var,)
        if isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Mod):
            if isinstance(arg.left, ast.Constant) and isinstance(arg.left.value, str):
                params = []
                if isinstance(arg.right, ast.Tuple):
                    params = [ast.unparse(elt) for elt in arg.right.elts]
                else:
                    params = [ast.unparse(arg.right)]
                return SQLInjectionFinding(
                    line_number=arg.lineno,
                    vulnerability_type="percent_format",
                    original_call="",
                    recommended_query=arg.left.value,
                    extracted_params=params,
                )

        # 3. .format() call: "SELECT ... {}".format(var)
        if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute) and arg.func.attr == "format":
            if isinstance(arg.func.value, ast.Constant) and isinstance(arg.func.value.value, str):
                template = arg.func.value.value.replace("{}", "%s")
                params = [ast.unparse(a) for a in arg.args]
                return SQLInjectionFinding(
                    line_number=arg.lineno,
                    vulnerability_type="str_format",
                    original_call="",
                    recommended_query=template,
                    extracted_params=params,
                )

        # 4. String concatenation: "SELECT ... WHERE id = " + user_id
        if isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Add):
            flattened = self._flatten_add(arg)
            if any(isinstance(node, ast.Constant) and isinstance(node.value, str) and "select" in node.value.lower() for node in flattened):
                parts = []
                params = []
                for node in flattened:
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        parts.append(node.value)
                    else:
                        parts.append("%s")
                        params.append(ast.unparse(node))
                return SQLInjectionFinding(
                    line_number=arg.lineno,
                    vulnerability_type="concat",
                    original_call="",
                    recommended_query="".join(parts),
                    extracted_params=params,
                )

        return None

    def _flatten_add(self, node: ast.AST) -> List[ast.AST]:
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return self._flatten_add(node.left) + self._flatten_add(node.right)
        return [node]


class SQLInjectionTransformer(ast.NodeTransformer):
    """Rewrites unsafe execute calls to use parameterized query tuples."""

    def __init__(self, findings: List[SQLInjectionFinding]) -> None:
        self.findings = findings
        self.patch_count = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        for finding in self.findings:
            if node.lineno == finding.line_number:
                # Replace with parameterized call: cursor.execute("SELECT ... %s", (param1, param2))
                new_query_arg = ast.Constant(value=finding.recommended_query)

                param_elts = [ast.parse(p, mode="eval").body for p in finding.extracted_params]
                params_tuple = ast.Tuple(elts=param_elts, ctx=ast.Load())

                # If single element, maintain tuple format
                node.args = [new_query_arg, params_tuple]
                self.patch_count += 1
                break
        return node


class SQLInjectionSynthesizer:
    """Orchestrator for SQL injection vulnerability detection and AST parameterization."""

    def analyze(self, source_code: str) -> List[SQLInjectionFinding]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return []
        visitor = SQLInjectionVisitor()
        visitor.visit(tree)
        return visitor.findings

    def synthesize(self, source_code: str) -> Tuple[str, List[SQLInjectionFinding]]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return source_code, []

        visitor = SQLInjectionVisitor()
        visitor.visit(tree)
        if not visitor.findings:
            return source_code, []

        transformer = SQLInjectionTransformer(visitor.findings)
        modified_tree = transformer.visit(tree)
        ast.fix_missing_locations(modified_tree)

        try:
            new_code = ast.unparse(modified_tree)
            # Verify compilation
            compile(new_code, "<healed_sql>", "exec")
            return new_code, visitor.findings
        except Exception:
            return source_code, visitor.findings


def synthesize_parameterized_queries(source_code: str) -> Tuple[str, List[SQLInjectionFinding]]:
    engine = SQLInjectionSynthesizer()
    return engine.synthesize(source_code)
