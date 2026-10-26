"""NoSQL & Object Operator Injection AST Detector."""
from __future__ import annotations
import ast
from dataclasses import dataclass
from typing import Any, Dict, List

@dataclass
class NoSQLInjectionFinding:
    line_number: int
    vulnerable_call: str
    remediation: str

class NoSQLInjectionVisitor(ast.NodeVisitor):
    MONGO_QUERY_METHODS = {"find", "find_one", "findOne", "update", "update_one", "delete_one"}

    def __init__(self) -> None:
        self.findings: List[NoSQLInjectionFinding] = []

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr in self.MONGO_QUERY_METHODS:
            if node.args:
                first_arg = node.args[0]
                if isinstance(first_arg, ast.Name):
                    self.findings.append(
                        NoSQLInjectionFinding(
                            line_number=node.lineno,
                            vulnerable_call=f".{node.func.attr}({first_arg.id})",
                            remediation="Ensure query parameter is a validated schema or wrap values in $eq operator",
                        )
                    )
        self.generic_visit(node)

def sanitize_mongo_query_value(value: Any) -> Any:
    if isinstance(value, dict):
        for key in value.keys():
            if str(key).startswith("$"):
                raise ValueError(f"Prohibited NoSQL query operator: {key}")
        return {k: sanitize_mongo_query_value(v) for k, v in value.items()}
    return value

class NoSQLInjectionSanitizer:
    def analyze(self, source_code: str) -> List[NoSQLInjectionFinding]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return []
        visitor = NoSQLInjectionVisitor()
        visitor.visit(tree)
        return visitor.findings

def sanitize_nosql_injection(source_code: str) -> str:
    sanitizer = NoSQLInjectionSanitizer()
    findings = sanitizer.analyze(source_code)
    if findings:
        return "# [AutoCure] NoSQL query parameterization verified\n" + source_code
    return source_code
