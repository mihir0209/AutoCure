"""Insecure Deserialization & Pickle Exploit AST Sanitizer.

Detects insecure object deserialization (pickle.loads, yaml.load without SafeLoader)
that permits arbitrary code execution, and synthesizes secure yaml.safe_load or
defensive json/HMAC deserialization guards.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple


@dataclass
class DeserializationFinding:
    line_number: int
    library: str  # "pickle", "yaml"
    unsafe_call: str
    vulnerability_reason: str
    recommended_call: str


class DeserializationVisitor(ast.NodeVisitor):
    """AST visitor that detects unsafe deserialization calls."""

    def __init__(self) -> None:
        self.findings: List[DeserializationFinding] = []

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            mod_id = node.func.value.id
            attr_name = node.func.attr

            # 1. pickle.loads or pickle.load
            if mod_id in {"pickle", "_pickle", "cPickle"} and attr_name in {"loads", "load"}:
                self.findings.append(
                    DeserializationFinding(
                        line_number=node.lineno,
                        library="pickle",
                        unsafe_call=ast.unparse(node),
                        vulnerability_reason="Unsafe pickle deserialization permits arbitrary remote code execution (RCE)",
                        recommended_call="json.loads or HMAC-verified deserialization",
                    )
                )

            # 2. yaml.load without SafeLoader
            elif mod_id in {"yaml", "ruamel_yaml"} and attr_name == "load":
                is_safe = False
                for kw in node.keywords:
                    if kw.arg == "Loader" and "safe" in ast.unparse(kw.value).lower():
                        is_safe = True
                        break
                if not is_safe:
                    self.findings.append(
                        DeserializationFinding(
                            line_number=node.lineno,
                            library="yaml",
                            unsafe_call=ast.unparse(node),
                            vulnerability_reason="Arbitrary object instantiation via unsafe yaml.load",
                            recommended_call="yaml.safe_load",
                        )
                    )

        self.generic_visit(node)


class DeserializationTransformer(ast.NodeTransformer):
    """AST transformer that converts unsafe deserialization calls into safe variants."""

    def __init__(self, findings: List[DeserializationFinding]) -> None:
        self.findings_by_line = {f.line_number: f for f in findings}
        self.patch_count = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        finding = self.findings_by_line.get(node.lineno)
        if finding:
            if finding.library == "yaml" and isinstance(node.func, ast.Attribute):
                # Replace yaml.load(...) with yaml.safe_load(data)
                node.func.attr = "safe_load"
                node.keywords = []  # Strip unsafe Loader kwarg
                self.patch_count += 1
            elif finding.library == "pickle" and isinstance(node.func, ast.Attribute):
                # Replace pickle.loads with json.loads
                if isinstance(node.func.value, ast.Name):
                    node.func.value.id = "json"
                    self.patch_count += 1
        return node


class DeserializationSanitizer:
    """Orchestrates detection and AST parameterization of insecure deserialization."""

    def analyze(self, source_code: str) -> List[DeserializationFinding]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return []
        visitor = DeserializationVisitor()
        visitor.visit(tree)
        return visitor.findings

    def synthesize(self, source_code: str) -> Tuple[str, List[DeserializationFinding]]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return source_code, []

        visitor = DeserializationVisitor()
        visitor.visit(tree)
        if not visitor.findings:
            return source_code, []

        transformer = DeserializationTransformer(visitor.findings)
        modified_tree = transformer.visit(tree)
        ast.fix_missing_locations(modified_tree)

        try:
            new_code = ast.unparse(modified_tree)
            compile(new_code, "<healed_deserialization>", "exec")
            return new_code, visitor.findings
        except Exception:
            return source_code, visitor.findings


def sanitize_deserialization(source_code: str) -> Tuple[str, List[DeserializationFinding]]:
    engine = DeserializationSanitizer()
    return engine.synthesize(source_code)
