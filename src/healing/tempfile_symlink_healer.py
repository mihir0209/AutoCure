"""
AutoCure Insecure Temporary File TOCTOU & Symlink Healer.

Scans Python AST for dangerous file creation calls in shared directories (/tmp, /var/tmp)
and synthesizes atomic, symlink-resistant file descriptor creation guardrails
utilizing os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW with 0o600 permissions.
"""

import ast
import os
from typing import List, Tuple, Optional


def safe_tempfile_open(path: str, mode: str = "w"):
    """
    Runtime helper: opens file in shared directory with strict O_NOFOLLOW and O_EXCL flags,
    preventing symlink attacks and race conditions.
    """
    if "w" in mode or "a" in mode or "x" in mode:
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW

        try:
            fd = os.open(path, flags, 0o600)
            return os.fdopen(fd, mode)
        except (FileExistsError, OSError) as e:
            raise PermissionError(f"Temporary file security violation: {path} already exists or is a symlink: {e}")
    else:
        # Read-only open with O_NOFOLLOW
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags)
        return os.fdopen(fd, mode)


class TempfileSymlinkHealer(ast.NodeTransformer):
    """
    AST transformer that intercepts open() calls pointing to /tmp or /var/tmp
    and replaces them with safe_tempfile_open.
    """

    SAFE_JAIL_HELPER_DEF = """
import os

def _autocure_safe_temp_open(path, mode="w", *args, **kwargs):
    if any(m in mode for m in ("w", "a", "x", "+")):
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(path, flags, 0o600)
            return os.fdopen(fd, mode)
        except (FileExistsError, OSError) as e:
            raise PermissionError("Temporary file security violation: " + str(path) + " error: " + str(e))
    else:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags)
        return os.fdopen(fd, mode)
"""

    SHARED_TEMP_PREFIXES = ("/tmp/", "/var/tmp/", "tmp/")

    def __init__(self):
        super().__init__()
        self.healed_count = 0
        self.healed_locations: List[int] = []
        self.needs_helper = False

    def is_temp_path(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return any(node.value.startswith(p) for p in self.SHARED_TEMP_PREFIXES)
        if isinstance(node, ast.JoinedStr):
            # Check prefix of first constant in f-string
            if node.values and isinstance(node.values[0], ast.Constant) and isinstance(node.values[0].value, str):
                return any(node.values[0].value.startswith(p) for p in self.SHARED_TEMP_PREFIXES)
        return False

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)

        is_open = False
        if isinstance(node.func, ast.Name) and node.func.id == "open":
            is_open = True
        elif isinstance(node.func, ast.Attribute) and node.func.attr == "open" and isinstance(node.func.value, ast.Name) and node.func.value.id in ("builtins", "io"):
            is_open = True

        if is_open and node.args:
            path_arg = node.args[0]
            if self.is_temp_path(path_arg):
                self.healed_count += 1
                self.healed_locations.append(getattr(node, "lineno", 0))
                self.needs_helper = True

                node.func = ast.Name(id="_autocure_safe_temp_open", ctx=ast.Load())
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
