from __future__ import annotations
import ast
from dataclasses import dataclass
from typing import List

@dataclass
class InsecureRandomFinding:
    line_number: int
    function_name: str
    remediation: str

SECURITY_SENSITIVE_TERMS = {"token", "key", "secret", "salt", "password", "session", "auth", "nonce", "otp"}

class InsecureRandomVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.findings: List[InsecureRandomFinding] = []
        self.current_function: str = ""

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        prev = self.current_function
        self.current_function = node.name.lower()
        self.generic_visit(node)
        self.current_function = prev

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute):
            # Check for random.randint, random.choice, random.random
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "random":
                if any(term in self.current_function for term in SECURITY_SENSITIVE_TERMS):
                    self.findings.append(
                        InsecureRandomFinding(
                            line_number=node.lineno,
                            function_name=node.func.attr,
                            remediation="Replace random pseudo-random generator with cryptographically secure secrets module equivalent"
                        )
                    )
        self.generic_visit(node)

def find_insecure_random_vulnerabilities(code: str) -> List[InsecureRandomFinding]:
    try:
        tree = ast.parse(code)
        visitor = InsecureRandomVisitor()
        visitor.visit(tree)
        return visitor.findings
    except SyntaxError:
        return []

def sanitize_random_code(code: str) -> str:
    # Transforms random.choice / random.randint / random.random to secrets equivalents
    transformed = code.replace("import random", "import secrets")
    transformed = transformed.replace("random.choice", "secrets.choice")
    transformed = transformed.replace("random.randint", "secrets.randbelow")
    transformed = transformed.replace("random.random()", "(secrets.randbelow(1000000) / 1000000.0)")
    return transformed
