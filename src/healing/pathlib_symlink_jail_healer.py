import os
import pathlib

def safe_resolve_symlink_jail(untrusted_path_str: str, jail_root_str: str) -> pathlib.Path:
    """
    Resolves symlinks strictly and validates that target path remains confined within jail root.
    """
    root = pathlib.Path(jail_root_str).resolve()
    target = (root / untrusted_path_str).resolve(strict=False)

    try:
        if not target.is_relative_to(root):
            raise PermissionError(f"Symlink jail escape detected: {target} outside {root}")
    except AttributeError:
        if os.path.commonpath([str(root), str(target)]) != str(root):
            raise PermissionError(f"Symlink jail escape detected: {target} outside {root}")

    return target
