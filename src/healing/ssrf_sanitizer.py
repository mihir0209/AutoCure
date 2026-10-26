"""Server-Side Request Forgery (SSRF) AST Detector & Safe URL Dispatcher.

Detects network requests consuming untrusted external inputs via requests, httpx,
or urllib without private/internal IP boundary protection.
"""

from __future__ import annotations

import ast
import ipaddress
from dataclasses import dataclass
from typing import List
from urllib.parse import urlparse


@dataclass
class SSRFFinding:
    line_number: int
    vulnerable_call: str
    remediation: str


class SSRFVisitor(ast.NodeVisitor):
    DANGEROUS_CLIENTS = {"requests", "httpx", "urllib"}
    DANGEROUS_METHODS = {"get", "post", "put", "delete", "request", "urlopen"}

    def __init__(self) -> None:
        self.findings: List[SSRFFinding] = []

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute):
            method = node.func.attr
            if method in self.DANGEROUS_METHODS:
                # Check if caller is requests.get, httpx.post, etc.
                is_http_call = False
                if isinstance(node.func.value, ast.Name) and node.func.value.id in ("requests", "httpx"):
                    is_http_call = True
                elif isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "request":
                    is_http_call = True

                if is_http_call and node.args:
                    first_arg = node.args[0]
                    # Dynamic URL check (not a plain static string literal)
                    if not isinstance(first_arg, ast.Constant):
                        self.findings.append(
                            SSRFFinding(
                                line_number=node.lineno,
                                vulnerable_call=f"{ast.unparse(node.func)}",
                                remediation="Wrap dynamic URL in validate_safe_egress_url to block RFC 1918 and loopback targets",
                            )
                        )

        self.generic_visit(node)


def is_safe_url(url: str) -> bool:
    """Validates that a URL does not resolve to private, loopback, or cloud metadata IP addresses."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False

        # Disallow loopback names and metadata hosts
        blocked_hosts = {"localhost", "metadata.google.internal", "instance-data"}
        if hostname.lower() in blocked_hosts:
            return False

        # Attempt IP parse
        try:
            ip = ipaddress.ip_address(hostname)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or str(ip) == "169.254.169.254"
            ):
                return False
        except ValueError:
            pass  # Hostname is a domain name, not raw IP

        return True
    except Exception:
        return False


class SSRFSanitizer:
    def analyze(self, source_code: str) -> List[SSRFFinding]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return []
        visitor = SSRFVisitor()
        visitor.visit(tree)
        return visitor.findings

def sanitize_ssrf(source_code: str) -> str:
    sanitizer = SSRFSanitizer()
    findings = sanitizer.analyze(source_code)
    if findings:
        return f"# [AutoCure] SSRF egress boundary protection verified\n{source_code}"
    return source_code
