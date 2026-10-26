"""Hardcoded Secrets & API Key AST Sanitizer & Environment Variable Extractor.

Detects high-entropy hardcoded secrets, API keys, private tokens, and credentials
statically assigned in source code. Synthesizes dynamic environment variable lookups
via `os.environ.get(...)` or `os.getenv(...)` to eliminate credential leaks in repositories.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any, List, Optional, Set, Tuple


@dataclass
class SecretFinding:
    line_number: int
    secret_var: str
    masked_secret: str
    vulnerability_reason: str
    remediation: str


class SecretsVisitor(ast.NodeVisitor):
    """AST visitor that detects hardcoded sensitive tokens and API keys."""

    SECRET_NAME_PATTERNS = re.compile(
        r"(api[_-]?key|secret[_-]?key|auth[_-]?token|access[_-]?token|private[_-]?key|"
        r"password|client[_-]?secret|aws[_-]?secret|encryption[_-]?key|stripe[_-]?secret)",
        re.IGNORECASE,
    )

    KNOWN_TOKEN_PATTERNS = re.compile(
        r"(sk_live_[0-9a-zA-Z]{16,}|ghp_[0-9a-zA-Z]{36}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA|EC|OPENSSH) PRIVATE KEY-----)",
    )

    def __init__(self) -> None:
        self.findings: List[SecretFinding] = []

    def _is_suspicious_secret(self, var_name: str, value_str: str) -> bool:
        if not isinstance(value_str, str):
            return False
        # Do not flag placeholders or trivial strings
        if len(value_str) < 8:
            return False
        if value_str.lower() in {"dummy", "placeholder", "changeme", "test", "your_secret_here", "password", "none"}:
            return False

        if self.KNOWN_TOKEN_PATTERNS.search(value_str):
            return True

        if self.SECRET_NAME_PATTERNS.search(var_name):
            # Check if it looks like a real value rather than empty / template
            if len(value_str) >= 8 and not value_str.startswith("YOUR_"):
                return True

        return False

    def visit_Assign(self, node: ast.Assign) -> None:
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            val_str = node.value.value
            for target in node.targets:
                if isinstance(target, ast.Name):
                    var_name = target.id
                    if self._is_suspicious_secret(var_name, val_str):
                        masked = val_str[:4] + "*" * max(0, len(val_str) - 8) + val_str[-4:] if len(val_str) >= 8 else "***"
                        self.findings.append(
                            SecretFinding(
                                line_number=node.lineno,
                                secret_var=var_name,
                                masked_secret=masked,
                                vulnerability_reason=f"Hardcoded sensitive credential '{var_name}' found in source code",
                                remediation=f"Extract to os.environ.get('{var_name}')",
                            )
                        )
        self.generic_visit(node)


class SecretsTransformer(ast.NodeTransformer):
    """AST transformer that converts hardcoded secret strings to os.environ.get calls."""

    def __init__(self, findings: List[SecretFinding]) -> None:
        self.findings_by_line = {f.line_number: f for f in findings}
        self.patch_count = 0
        self.needs_os_import = False

    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        self.generic_visit(node)
        finding = self.findings_by_line.get(node.lineno)
        if not finding:
            return node

        # Transform value to os.environ.get("VAR_NAME")
        env_call = ast.Call(
            func=ast.Attribute(
                value=ast.Attribute(
                    value=ast.Name(id="os", ctx=ast.Load()),
                    attr="environ",
                    ctx=ast.Load(),
                ),
                attr="get",
                ctx=ast.Load(),
            ),
            args=[ast.Constant(value=finding.secret_var)],
            keywords=[],
        )
        node.value = env_call
        self.needs_os_import = True
        self.patch_count += 1
        return node


class SecretsSanitizer:
    """Orchestrates detection and extraction of hardcoded secrets."""

    def analyze(self, source_code: str) -> List[SecretFinding]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return []
        visitor = SecretsVisitor()
        visitor.visit(tree)
        return visitor.findings

    def synthesize(self, source_code: str) -> Tuple[str, List[SecretFinding]]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return source_code, []

        visitor = SecretsVisitor()
        visitor.visit(tree)
        if not visitor.findings:
            return source_code, []

        transformer = SecretsTransformer(visitor.findings)
        modified_tree = transformer.visit(tree)

        # Check existing imports for 'os'
        has_os = False
        for stmt in modified_tree.body:
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    if alias.name == "os":
                        has_os = True
            elif isinstance(stmt, ast.ImportFrom) and stmt.module == "os":
                has_os = True

        if transformer.needs_os_import and not has_os:
            modified_tree.body = [ast.Import(names=[ast.alias(name="os")])] + modified_tree.body

        ast.fix_missing_locations(modified_tree)

        try:
            new_code = ast.unparse(modified_tree)
            compile(new_code, "<healed_secrets>", "exec")
            return new_code, visitor.findings
        except Exception:
            return source_code, visitor.findings


def sanitize_secrets(source_code: str) -> Tuple[str, List[SecretFinding]]:
    engine = SecretsSanitizer()
    return engine.synthesize(source_code)
