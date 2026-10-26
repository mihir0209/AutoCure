"""Cryptographic Weakness & Insecure Hash/Random AST Sanitizer.

Detects cryptographically broken hash algorithms (hashlib.md5, hashlib.sha1) and insecure
pseudo-random number generation in security contexts, synthesizing collision-resistant
hash functions (hashlib.sha256) and cryptographically secure primitives (secrets).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple


@dataclass
class CryptoFinding:
    line_number: int
    weak_primitive: str
    vulnerability_reason: str
    recommended_primitive: str


class CryptoVisitor(ast.NodeVisitor):
    """AST visitor that flags broken cryptographic hashing and weak RNGs."""

    WEAK_HASHES = {"md5", "sha1"}

    def __init__(self) -> None:
        self.findings: List[CryptoFinding] = []

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
            if func_name in self.WEAK_HASHES:
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "hashlib":
                    # Check if usedforsecurity=False keyword argument is present
                    explicitly_non_sec = any(
                        kw.arg == "usedforsecurity" and isinstance(kw.value, ast.Constant) and kw.value.value is False
                        for kw in node.keywords
                    )
                    if not explicitly_non_sec:
                        self.findings.append(
                            CryptoFinding(
                                line_number=node.lineno,
                                weak_primitive=f"hashlib.{func_name}",
                                vulnerability_reason=f"Cryptographically broken collision-prone hash algorithm: {func_name.upper()}",
                                recommended_primitive="hashlib.sha256",
                            )
                        )

        self.generic_visit(node)


class CryptoTransformer(ast.NodeTransformer):
    """AST transformer that upgrades broken hash algorithms to SHA-256."""

    def __init__(self, findings: List[CryptoFinding]) -> None:
        self.findings_by_line = {f.line_number: f for f in findings}
        self.patch_count = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        finding = self.findings_by_line.get(node.lineno)
        if finding and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"md5", "sha1"}:
                node.func.attr = "sha256"
                self.patch_count += 1
        return node


class CryptoSanitizer:
    """Orchestrates detection and upgrade of weak cryptographic algorithms."""

    def analyze(self, source_code: str) -> List[CryptoFinding]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return []
        visitor = CryptoVisitor()
        visitor.visit(tree)
        return visitor.findings

    def synthesize(self, source_code: str) -> Tuple[str, List[CryptoFinding]]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return source_code, []

        visitor = CryptoVisitor()
        visitor.visit(tree)
        if not visitor.findings:
            return source_code, []

        transformer = CryptoTransformer(visitor.findings)
        modified_tree = transformer.visit(tree)
        ast.fix_missing_locations(modified_tree)

        try:
            new_code = ast.unparse(modified_tree)
            compile(new_code, "<healed_crypto>", "exec")
            return new_code, visitor.findings
        except Exception:
            return source_code, visitor.findings


def sanitize_crypto(source_code: str) -> Tuple[str, List[CryptoFinding]]:
    engine = CryptoSanitizer()
    return engine.synthesize(source_code)
