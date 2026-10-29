import re

def sanitize_ldap_search_filter(raw_input: str) -> str:
    r"""
    Escapes RFC 4515 special filter characters: *, (, ), \, NUL
    r"""
    if not isinstance(raw_input, str):
        return ""
    # Escape backslash first
    sanitized = raw_input.replace("\\", r"\5c")
    sanitized = sanitized.replace("*", r"\2a")
    sanitized = sanitized.replace("(", r"\28")
    sanitized = sanitized.replace(")", r"\29")
    sanitized = sanitized.replace("\x00", r"\00")
    return sanitized
