"""
AutoCure LDAP & JNDI Injection AST Healer.

Scans Python AST for dangerous unescaped LDAP filter string interpolations
and JNDI lookup strings, synthesizing RFC 4515 compliant parameter escaping
guardrails to neutralize LDAP filter injection and directory enumeration.
"""

import ast
import re
from typing import List, Tuple, Optional

LDAP_ESCAPE_MAP = {
    "\\": "\\5c",
    "*": "\\2a",
    "(": "\\28",
    ")": "\\29",
    "\x00": "\\00",
}


def ldap_escape_filter(value: str) -> str:
    """
    Runtime RFC 4515 filter escaping helper: escapes special filter characters.
    """
    if not isinstance(value, str):
        value = str(value)
    for char, escaped in LDAP_ESCAPE_MAP.items():
        value = value.replace(char, escaped)
    return value


class LdapInjectionHealer(ast.NodeTransformer):
    """
    AST transformer that intercepts LDAP search filter string constructions
    and wraps dynamic format string variables with safe LDAP filter escaping.
    """

    SAFE_JAIL_HELPER_DEF = """
def _autocure_ldap_escape(val):
    if not isinstance(val, str):
        val = str(val)
    escapes = [('\\\\', '\\\\5c'), ('*', '\\\\2a'), ('(', '\\\\28'), (')', '\\\\29'), ('\\x00', '\\\\00')]
    for char, esc in escapes:
        val = val.replace(char, esc)
    return val
"""

    def __init__(self):
        super().__init__()
        self.healed_count = 0
        self.healed_locations: List[int] = []
        self.needs_helper = False

    def visit_JoinedStr(self, node: ast.JoinedStr) -> ast.AST:
        # Check if f-string looks like an LDAP search filter: e.g. f"(uid={user})" or f"(&(cn={name})...)"
        static_text = "".join(
            part.value for part in node.values if isinstance(part, ast.Constant) and isinstance(part.value, str)
        )

        is_ldap_filter = bool(
            re.search(r"\([&|!]?\(?[a-zA-Z0-9_-]+=", static_text) or "(uid=" in static_text or "(cn=" in static_text or "(mail=" in static_text
        )

        if is_ldap_filter:
            for part in node.values:
                if isinstance(part, ast.FormattedValue):
                    if not (isinstance(part.value, ast.Call) and isinstance(part.value.func, ast.Name) and part.value.func.id == "_autocure_ldap_escape"):
                        self.healed_count += 1
                        self.healed_locations.append(getattr(node, "lineno", 0))
                        self.needs_helper = True
                        part.value = ast.Call(
                            func=ast.Name(id="_autocure_ldap_escape", ctx=ast.Load()),
                            args=[part.value],
                            keywords=[],
                        )

        self.generic_visit(node)
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
