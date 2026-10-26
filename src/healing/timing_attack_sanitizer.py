from __future__ import annotations
import ast
import hmac
from dataclasses import dataclass
from typing import List, Union

@dataclass
class TimingAttackFinding:
    line_number: int
    compared_variable: str
    remediation: str

SENSITIVE_COMPARISON_TERMS = {"token", "secret", "signature", "digest", "hash", "api_key", "hmac", "password"}

class TimingAttackVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.findings: List[TimingAttackFinding] = []

    def visit_Compare(self, node: ast.Compare) -> None:
        # Detect non-constant-time comparison == on sensitive terms
        for op in node.ops:
            if isinstance(op, (ast.Eq, ast.NotEq)):
                # Inspect left and right variables
                left_name = ""
                if isinstance(node.left, ast.Name):
                    left_name = node.left.id.lower()
                
                right_names = []
                for comp in node.comparators:
                    if isinstance(comp, ast.Name):
                        right_names.append(comp.id.lower())

                all_names = [left_name] + right_names
                if any(any(term in name for term in SENSITIVE_COMPARISON_TERMS) for name in all_names if name):
                    self.findings.append(
                        TimingAttackFinding(
                            line_number=node.lineno,
                            compared_variable=left_name or "comparator",
                            remediation="Use hmac.compare_digest() for constant-time secret comparison to prevent side-channel timing attacks"
                        )
                    )
        self.generic_visit(node)

def find_timing_attack_vulnerabilities(code: str) -> List[TimingAttackFinding]:
    try:
        tree = ast.parse(code)
        visitor = TimingAttackVisitor()
        visitor.visit(tree)
        return visitor.findings
    except SyntaxError:
        return []

def safe_constant_time_compare(val1: Union[str, bytes], val2: Union[str, bytes]) -> bool:
    if isinstance(val1, str):
        val1 = val1.encode("utf-8")
    if isinstance(val2, str):
        val2 = val2.encode("utf-8")
    return hmac.compare_digest(val1, val2)
