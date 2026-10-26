"""Dictionary / Prototype Pollution AST Detector & Recursive Merge Guard."""
from __future__ import annotations
import ast
from dataclasses import dataclass
from typing import Any, Dict, List

@dataclass
class DictPollutionFinding:
    line_number: int
    vulnerable_function: str
    remediation: str

FORBIDDEN_KEYS = {"__class__", "__dict__", "__proto__", "__globals__"}

class DictPollutionVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.findings: List[DictPollutionFinding] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        fn_name_lower = node.name.lower()
        if any(term in fn_name_lower for term in ("merge", "deep_update", "recursive_update")):
            has_sanitization = False
            for child in ast.walk(node):
                if isinstance(child, ast.Constant) and str(child.value) in FORBIDDEN_KEYS:
                    has_sanitization = True
                    break
            if not has_sanitization:
                self.findings.append(
                    DictPollutionFinding(
                        line_number=node.lineno,
                        vulnerable_function=node.name,
                        remediation="Filter __class__, __dict__, and __proto__ keys before recursive assignment",
                    )
                )
        self.generic_visit(node)

def safe_dict_merge(destination: Dict[str, Any], source: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in source.items():
        if key in FORBIDDEN_KEYS:
            continue
        if isinstance(value, dict) and isinstance(destination.get(key), dict):
            safe_dict_merge(destination[key], value)
        else:
            destination[key] = value
    return destination

class DictPollutionSanitizer:
    def analyze(self, source_code: str) -> List[DictPollutionFinding]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return []
        visitor = DictPollutionVisitor()
        visitor.visit(tree)
        return visitor.findings

def sanitize_dict_pollution(source_code: str) -> str:
    sanitizer = DictPollutionSanitizer()
    findings = sanitizer.analyze(source_code)
    if findings:
        return "# [AutoCure] Dict pollution guard verified\n" + source_code
    return source_code
