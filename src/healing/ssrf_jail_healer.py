"""
SSRF Dynamic URL IP Validator & Localhost Metadata Jail AST Healer.

Scans Python AST for outbound HTTP requests (requests.get, requests.post,
urllib.request.urlopen, httpx.get) using untrusted or dynamic URLs that may
reach internal loopbacks, private RFC 1918 subnets, or cloud metadata endpoints
(169.254.169.254), and synthesizes safe DNS validation guardrails.
"""

import ast
from typing import Tuple, List, Optional
from urllib.parse import urlparse
import socket
import ipaddress


def ssrf_jail(url: str, allowed_schemes=("http", "https")) -> str:
    """
    Runtime jail helper: parses url, resolves DNS hostname synchronously,
    and blocks loopbacks, private networks, and cloud instance metadata.
    """
    if not isinstance(url, str):
        url = str(url)

    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in allowed_schemes:
        raise PermissionError(f"SSRF blocked: Disallowed scheme '{scheme}'")

    hostname = parsed.hostname
    if not hostname:
        raise PermissionError("SSRF blocked: Missing hostname in URL")

    # Reject localhost aliases directly
    lower_host = hostname.lower()
    if lower_host in ("localhost", "127.0.0.1", "::1", "169.254.169.254", "0.0.0.0"):
        raise PermissionError(f"SSRF blocked: Access to localhost or cloud metadata '{hostname}' is forbidden")

    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise PermissionError(f"SSRF blocked: DNS resolution failed for '{hostname}': {e}")

    for family, _, _, _, sockaddr in addr_info:
        ip_str = sockaddr[0]
        ip = ipaddress.ip_address(ip_str)

        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or str(ip) == "169.254.169.254"
        ):
            raise PermissionError(f"SSRF blocked: Hostname '{hostname}' resolves to restricted IP {ip_str}")

    return url


class SSRFJailHealer(ast.NodeTransformer):
    """
    AST transformer that intercepts unconfined HTTP request calls with dynamic URLs
    and wraps them with runtime SSRF jail validation.
    """

    SAFE_JAIL_HELPER_DEF = """
import urllib.parse
import socket
import ipaddress

def _autocure_ssrf_jail(url, allowed_schemes=("http", "https")):
    if not isinstance(url, str):
        url = str(url)
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in allowed_schemes:
        raise PermissionError("SSRF blocked: Disallowed scheme " + str(scheme))
    hostname = parsed.hostname
    if not hostname:
        raise PermissionError("SSRF blocked: Missing hostname in URL")
    lower_host = hostname.lower()
    if lower_host in ("localhost", "127.0.0.1", "::1", "169.254.169.254", "0.0.0.0"):
        raise PermissionError("SSRF blocked: Access to localhost or cloud metadata is forbidden: " + str(hostname))
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise PermissionError("SSRF blocked: DNS resolution failed: " + str(e))
    for family, _, _, _, sockaddr in addr_info:
        ip_str = sockaddr[0]
        ip = ipaddress.ip_address(ip_str)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or str(ip) == "169.254.169.254":
            raise PermissionError("SSRF blocked: Hostname resolves to restricted IP: " + str(ip_str))
    return url
"""

    HTTP_CALL_ATTRS = {"get", "post", "put", "delete", "patch", "head", "request"}
    HTTP_CLIENTS = {"requests", "httpx", "aiohttp"}

    def __init__(self):
        super().__init__()
        self.healed_count = 0
        self.healed_locations: List[int] = []
        self.needs_helper = False

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)

        is_http_call = False

        if isinstance(node.func, ast.Attribute):
            if node.func.attr in self.HTTP_CALL_ATTRS:
                if isinstance(node.func.value, ast.Name) and node.func.value.id in self.HTTP_CLIENTS:
                    is_http_call = True

        if isinstance(node.func, ast.Attribute) and node.func.attr == "urlopen":
            is_http_call = True
        elif isinstance(node.func, ast.Name) and node.func.id == "urlopen":
            is_http_call = True

        if is_http_call and node.args:
            url_arg = node.args[0]

            is_dynamic = not (
                isinstance(url_arg, ast.Constant)
                and isinstance(url_arg.value, str)
                and not url_arg.value.startswith(("http://127.", "http://localhost", "http://169.254."))
            )

            if is_dynamic:
                self.healed_count += 1
                self.healed_locations.append(node.lineno if hasattr(node, "lineno") else 0)
                self.needs_helper = True

                node.args[0] = ast.Call(
                    func=ast.Name(id="_autocure_ssrf_jail", ctx=ast.Load()),
                    args=[url_arg],
                    keywords=[],
                )
                return node

        return node

    def heal_source(self, source_code: str) -> Tuple[str, int]:
        self.healed_count = 0
        self.healed_locations = []
        self.needs_helper = False

        tree = ast.parse(source_code)
        healed_tree = self.visit(tree)

        if self.healed_count == 0:
            return source_code, 0

        if self.needs_helper:
            helper_ast = ast.parse(self.SAFE_JAIL_HELPER_DEF).body
            healed_tree.body = helper_ast + healed_tree.body

        ast.fix_missing_locations(healed_tree)
        healed_source = ast.unparse(healed_tree)
        return healed_source, self.healed_count
