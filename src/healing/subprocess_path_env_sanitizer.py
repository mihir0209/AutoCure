import os
import re

def sanitize_subprocess_path_env(raw_path_env: str) -> str:
    """
    Sanitizes PATH environment variable: strips relative directories ('.', '..')
    and unquoted insecure directories prone to local binary hijacking.
    """
    if not isinstance(raw_path_env, str):
        return "/usr/bin:/bin"
    delimiter = ";" if os.name == "nt" else ":"
    entries = raw_path_env.split(delimiter)
    clean_entries = []

    for entry in entries:
        stripped = entry.strip().strip("'\"")
        # Reject current directory, relative paths, or empty strings
        if stripped in (".", "..", "") or stripped.startswith("./") or stripped.startswith("../"):
            continue
        clean_entries.append(stripped)

    return delimiter.join(clean_entries)
