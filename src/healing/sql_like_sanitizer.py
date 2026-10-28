"""
AutoCure SQL LIKE Wildcard Injection Sanitizer.
Escapes '%' and '_' characters to prevent wildcard denial-of-service and enumeration.
"""
def sanitize_like_pattern(pattern: str, escape_char: str = "\\") -> str:
    if not isinstance(pattern, str):
        pattern = str(pattern)
    escaped = pattern.replace(escape_char, escape_char + escape_char)
    escaped = escaped.replace("%", escape_char + "%")
    escaped = escaped.replace("_", escape_char + "_")
    return escaped
