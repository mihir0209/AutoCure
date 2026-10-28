import re

def sanitize_nested_redos_pattern(regex_pattern: str) -> str:
    if not isinstance(regex_pattern, str):
        return ""
    # Simplify nested repeated quantifiers like (x+)+ to x+
    sanitized = re.sub(r"\((.+?)[+*]\)[+*]", r"\1+", regex_pattern)
    return sanitized
