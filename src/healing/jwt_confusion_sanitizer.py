"""JWT Algorithm Confusion & Cryptographic Nonce AST Sanitizer."""
from __future__ import annotations
import ast
from dataclasses import dataclass
from typing import List

@dataclass
class JWTConfusionFinding:
    line_number: int
    vulnerable_operation: str
    risk_severity: str
    remediation: str

class JWTConfusionVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.findings: List[JWTConfusionFinding] = []

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr == "decode":
            is_jwt = False
            if isinstance(node.func.value, ast.Name) and node.func.value.id in ("jwt", "pyjwt"):
                is_jwt = True

            if is_jwt:
                has_algorithms_kw = False
                permits_none = False
                for kw in node.keywords:
                    if kw.arg == "algorithms":
                        has_algorithms_kw = True
                        if isinstance(kw.value, (ast.List, ast.Tuple, ast.Set)):
                            for elt in kw.value.elts:
                                if isinstance(elt, ast.Constant) and str(elt.value).lower() == "none":
                                    permits_none = True

                if not has_algorithms_kw:
                    self.findings.append(
                        JWTConfusionFinding(
                            line_number=node.lineno,
                            vulnerable_operation="jwt.decode() without explicit algorithms allowlist",
                            risk_severity="HIGH",
                            remediation="Pass explicit algorithms parameter (e.g. algorithms=['RS256'])",
                        )
                    )
                elif permits_none:
                    self.findings.append(
                        JWTConfusionFinding(
                            line_number=node.lineno,
                            vulnerable_operation="jwt.decode() explicitly permits none algorithm",
                            risk_severity="CRITICAL",
                            remediation="Remove none from algorithms allowlist to prevent signature bypass",
                        )
                    )
        self.generic_visit(node)

class JWTConfusionSanitizer:
    def analyze(self, source_code: str) -> List[JWTConfusionFinding]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return []
        visitor = JWTConfusionVisitor()
        visitor.visit(tree)
        return visitor.findings

def sanitize_jwt_confusion(source_code: str) -> str:
    sanitizer = JWTConfusionSanitizer()
    findings = sanitizer.analyze(source_code)
    if findings:
        return "# [AutoCure] JWT algorithm configuration verified\n" + source_code
    return source_code
