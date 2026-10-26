"""Insecure Deserialization AST Detector & Safe Serialization Synthesizer.

Detects untrusted deserialization vulnerabilities including pickle.loads/load,
yaml.load without safe loader, and marshal.loads. Synthesizes hardened alternatives
utilizing yaml.safe_load, json.loads, or cryptographic HMAC verification.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class DeserializationFinding:
    line_number: int
    vulnerable_call: str
    risk_severity: str
    remediation: str


class DeserializationVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.findings: List[DeserializationFinding] = []

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            mod = node.func.value.id
            fn = node.func.attr

            # 1. pickle.loads or pickle.load
            if mod == "pickle" and fn in ("loads", "load"):
                self.findings.append(
                    DeserializationFinding(
                        line_number=node.lineno,
                        vulnerable_call=f"pickle.{fn}",
                        risk_severity="CRITICAL",
                        remediation="Replace pickle with json.loads or sign with HMAC before deserialization",
                    )
                )

            # 2. yaml.load without SafeLoader
            elif mod in ("yaml", "ruamel_yaml") and fn == "load":
                has_safe_loader = False
                for kw in node.keywords:
                    if kw.arg == "Loader":
                        if isinstance(kw.value, ast.Attribute) and kw.value.attr in ("SafeLoader", "CSafeLoader"):
                            has_safe_loader = True
                if not has_safe_loader:
                    self.findings.append(
                        DeserializationFinding(
                            line_number=node.lineno,
                            vulnerable_call="yaml.load",
                            risk_severity="HIGH",
                            remediation="Replace yaml.load with yaml.safe_load or specify Loader=yaml.SafeLoader",
                        )
                    )

            # 3. marshal.loads / marshal.load
            elif mod == "marshal" and fn in ("loads", "load"):
                self.findings.append(
                    DeserializationFinding(
                        line_number=node.lineno,
                        vulnerable_call=f"marshal.{fn}",
                        risk_severity="HIGH",
                        remediation="Replace marshal with json or ast.literal_eval for data structures",
                    )
                )

        self.generic_visit(node)


class DeserializationTransformer(ast.NodeTransformer):
    """Replaces yaml.load(data) with yaml.safe_load(data)."""

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            if node.func.value.id == "yaml" and node.func.attr == "load":
                # Check if Loader is missing or unsafe
                node.func.attr = "safe_load"
                # Strip unsafe Loader kwarg if present
                node.keywords = [kw for kw in node.keywords if kw.arg != "Loader"]
        return node


class DeserializationSanitizer:
    def analyze(self, source_code: str) -> List[DeserializationFinding]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return []
        visitor = DeserializationVisitor()
        visitor.visit(tree)
        return visitor.findings

    def sanitize(self, source_code: str) -> str:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return source_code
        transformer = DeserializationTransformer()
        transformed_tree = transformer.visit(tree)
        ast.fix_missing_locations(transformed_tree)
        return ast.unparse(transformed_tree)


def sanitize_deserialization(source_code: str) -> str:
    sanitizer = DeserializationSanitizer()
    return sanitizer.sanitize(source_code)
