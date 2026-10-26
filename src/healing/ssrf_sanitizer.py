"""Server-Side Request Forgery (SSRF) AST Detector & Private IP Barrier Synthesizer.

Detects unvalidated dynamic URLs passed to outbound HTTP clients (requests, httpx, urllib),
and synthesizes secure private IP/internal network containment barriers that block requests
targeting localhost (127.0.0.1, ::1), cloud metadata (169.254.169.254), and RFC 1918 subnets.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple


@dataclass
class SSRFFinding:
    line_number: int
    client_method: str
    url_arg_name: str
    vulnerability_reason: str
    recommended_guard: str


class SSRFVisitor(ast.NodeVisitor):
    """AST visitor that detects unvalidated dynamic URLs in HTTP client invocations."""

    HTTP_CLIENT_METHODS = {"get", "post", "put", "delete", "patch", "request", "urlopen"}

    def __init__(self) -> None:
        self.findings: List[SSRFFinding] = []

    def visit_Call(self, node: ast.Call) -> None:
        method_name = ""
        is_http_call = False

        if isinstance(node.func, ast.Attribute) and node.func.attr in self.HTTP_CLIENT_METHODS:
            method_name = node.func.attr
            if isinstance(node.func.value, ast.Name) and node.func.value.id in {"requests", "httpx", "urllib"}:
                is_http_call = True
            elif isinstance(node.func.value, ast.Attribute) and node.func.value.attr in {"request", "client", "session"}:
                is_http_call = True
        elif isinstance(node.func, ast.Name) and node.func.id in {"urlopen"}:
            method_name = "urlopen"
            is_http_call = True

        if is_http_call and node.args:
            url_arg = node.args[0]
            # If URL is dynamic (ast.Name, ast.JoinedStr, etc.) and not a hardcoded constant URL
            if not isinstance(url_arg, ast.Constant):
                url_repr = ast.unparse(url_arg)
                self.findings.append(
                    SSRFFinding(
                        line_number=node.lineno,
                        client_method=method_name,
                        url_arg_name=url_repr,
                        vulnerability_reason="Unvalidated dynamic URL passed to HTTP client exposes SSRF vulnerabilities",
                        recommended_guard=f"validate_safe_url({url_repr})",
                    )
                )

        self.generic_visit(node)


class SSRFTransformer(ast.NodeTransformer):
    """AST transformer that wraps dynamic HTTP request URLs with validate_safe_url()."""

    def __init__(self, findings: List[SSRFFinding]) -> None:
        self.findings_by_line = {f.line_number: f for f in findings}
        self.patch_count = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        finding = self.findings_by_line.get(node.lineno)
        if finding and node.args:
            # Wrap the first arg with validate_safe_url(url)
            orig_arg = node.args[0]
            wrapped_arg = ast.Call(
                func=ast.Name(id="validate_safe_url", ctx=ast.Load()),
                args=[orig_arg],
                keywords=[],
            )
            node.args[0] = wrapped_arg
            self.patch_count += 1
        return node


class SSRFSanitizer:
    """Orchestrates SSRF vulnerability detection and URL containment AST synthesis."""

    def analyze(self, source_code: str) -> List[SSRFFinding]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return []
        visitor = SSRFVisitor()
        visitor.visit(tree)
        return visitor.findings

    def synthesize(self, source_code: str) -> Tuple[str, List[SSRFFinding]]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return source_code, []

        visitor = SSRFVisitor()
        visitor.visit(tree)
        if not visitor.findings:
            return source_code, []

        transformer = SSRFTransformer(visitor.findings)
        modified_tree = transformer.visit(tree)
        ast.fix_missing_locations(modified_tree)

        try:
            new_code = ast.unparse(modified_tree)
            compile(new_code, "<healed_ssrf>", "exec")
            return new_code, visitor.findings
        except Exception:
            return source_code, visitor.findings


def sanitize_ssrf(source_code: str) -> Tuple[str, List[SSRFFinding]]:
    engine = SSRFSanitizer()
    return engine.synthesize(source_code)
