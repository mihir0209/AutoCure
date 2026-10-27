"""
AutoCure Open Redirect & Domain Confinement AST Healer.

Scans Python AST for dangerous unvalidated HTTP redirect calls (Flask redirect,
Django HttpResponseRedirect, FastAPI RedirectResponse) using dynamic user-controlled
URLs, synthesizing safe same-origin and allowlisted domain confinement guardrails.
"""

import ast
from urllib.parse import urlparse
from typing import List, Tuple, Optional, Set


def safe_redirect(target_url: str, allowed_hosts: Optional[Set[str]] = None, fallback: str = "/") -> str:
    """
    Runtime validator for HTTP redirection targets.
    Neutralizes open redirects, protocol-relative attacks (//evil.com), and non-http schemes.
    """
    if not isinstance(target_url, str) or not target_url.strip():
        return fallback

    target_url = target_url.strip()

    # Disallow protocol-relative URLs (e.g. //evil.com or /\evil.com)
    if target_url.startswith(("//", "/\\", "\\\\", "\\/")):
        return fallback

    # Relative paths starting with a single '/' and not '//' are inherently same-origin
    if target_url.startswith("/") and not target_url.startswith(("//", "/\\")):
        return target_url

    parsed = urlparse(target_url)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return fallback

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return fallback

    if allowed_hosts:
        allowed_lower = {h.lower() for h in allowed_hosts}
        if hostname not in allowed_lower and not any(hostname.endswith("." + h) for h in allowed_lower):
            return fallback

    return target_url


class OpenRedirectHealer(ast.NodeTransformer):
    """
    AST transformer that intercepts redirect() calls and wraps dynamic target URLs
    with _autocure_safe_redirect validation.
    """

    SAFE_JAIL_HELPER_DEF = """
import urllib.parse

def _autocure_safe_redirect(target_url, allowed_hosts=None, fallback="/"):
    if not isinstance(target_url, str) or not target_url.strip():
        return fallback
    target_url = target_url.strip()
    if target_url.startswith(("//", "/\\\\", "\\\\\\\\", "\\\\/")):
        return fallback
    if target_url.startswith("/") and not target_url.startswith(("//", "/\\\\")):
        return target_url
    parsed = urllib.parse.urlparse(target_url)
    if parsed.scheme.lower() not in ("http", "https"):
        return fallback
    host = (parsed.hostname or "").lower()
    if not host:
        return fallback
    if allowed_hosts:
        allowed = {h.lower() for h in allowed_hosts}
        if host not in allowed and not any(host.endswith("." + h) for h in allowed):
            return fallback
    return target_url
"""

    REDIRECT_CALL_NAMES = {"redirect", "HttpResponseRedirect", "RedirectResponse"}

    def __init__(self):
        super().__init__()
        self.healed_count = 0
        self.healed_locations: List[int] = []
        self.needs_helper = False

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)

        is_redirect = False
        if isinstance(node.func, ast.Name) and node.func.id in self.REDIRECT_CALL_NAMES:
            is_redirect = True
        elif isinstance(node.func, ast.Attribute) and node.func.attr in self.REDIRECT_CALL_NAMES:
            is_redirect = True

        if is_redirect and node.args:
            url_arg = node.args[0]
            # If url_arg is a static string constant (e.g. redirect("/login")), it is safe.
            # But if it's dynamic (variable, call, subscript, binary op), heal it!
            is_static_safe = isinstance(url_arg, ast.Constant) and isinstance(url_arg.value, str) and url_arg.value.startswith("/") and not url_arg.value.startswith("//")

            if not is_static_safe:
                self.healed_count += 1
                self.healed_locations.append(getattr(node, "lineno", 0))
                self.needs_helper = True

                node.args[0] = ast.Call(
                    func=ast.Name(id="_autocure_safe_redirect", ctx=ast.Load()),
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
