from __future__ import annotations
import ast
from dataclasses import dataclass
from typing import List

@dataclass
class TempfileFinding:
    line_number: int
    vulnerability_type: str
    remediation: str

class TempfileVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.findings: List[TempfileFinding] = []

    def visit_Call(self, node: ast.Call) -> None:
        # Detect tempfile.mktemp()
        if isinstance(node.func, ast.Attribute):
            if node.func.attr == "mktemp":
                self.findings.append(
                    TempfileFinding(
                        line_number=node.lineno,
                        vulnerability_type="INSECURE_MKTEMP",
                        remediation="Replace mktemp() with NamedTemporaryFile() to prevent TOCTOU race condition"
                    )
                )
        self.generic_visit(node)

def find_tempfile_vulnerabilities(code: str) -> List[TempfileFinding]:
    try:
        tree = ast.parse(code)
        visitor = TempfileVisitor()
        visitor.visit(tree)
        return visitor.findings
    except SyntaxError:
        return []

def sanitize_tempfile_code(code: str) -> str:
    # Transforms mktemp() to NamedTemporaryFile(delete=False).name
    transformed = code.replace("tempfile.mktemp()", "tempfile.NamedTemporaryFile(delete=False).name")
    transformed = transformed.replace("mktemp()", "NamedTemporaryFile(delete=False).name")
    return transformed
