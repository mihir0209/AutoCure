import re

def sanitize_tempfile_suffix(suffix: str) -> str:
    if not isinstance(suffix, str):
        return ".tmp"
    if "/" in suffix or "\\" in suffix or ".." in suffix:
        return ".tmp"
    clean = re.sub(r"[^a-zA-Z0-9_.-]", "", suffix)
    if not clean.startswith("."):
        clean = "." + clean
    return clean
