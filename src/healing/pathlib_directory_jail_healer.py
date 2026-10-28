import pathlib
import os

def safe_resolve_pathlib_jail(untrusted_path_str: str, sandbox_root_str: str) -> pathlib.Path:
    sandbox_root = pathlib.Path(sandbox_root_str).resolve()
    target_path = (sandbox_root / untrusted_path_str).resolve()

    try:
        # Python 3.9+ is_relative_to
        if not target_path.is_relative_to(sandbox_root):
            raise PermissionError(f"Pathlib jail escape detected: {target_path} outside {sandbox_root}")
    except AttributeError:
        # Fallback for older python
        if os.path.commonpath([str(sandbox_root), str(target_path)]) != str(sandbox_root):
            raise PermissionError(f"Pathlib jail escape detected: {target_path} outside {sandbox_root}")

    return target_path
