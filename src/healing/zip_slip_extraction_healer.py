import os
import pathlib

def safe_extract_archive_member(target_dir: str, member_path: str) -> str:
    base = pathlib.Path(target_dir).resolve()
    dest = (base / member_path).resolve()
    try:
        if not dest.is_relative_to(base):
            raise PermissionError(f"Zip slip path traversal detected: {member_path} escapes {base}")
    except AttributeError:
        if os.path.commonpath([str(base), str(dest)]) != str(base):
            raise PermissionError(f"Zip slip path traversal detected: {member_path} escapes {base}")
    return str(dest)
