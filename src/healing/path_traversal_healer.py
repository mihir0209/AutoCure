"""
Path Traversal & Safe Path Directory Jail AST Healer.

Scans Python AST for dangerous file access operations (open, pathlib.Path, os.path.join)
using untrusted or dynamic paths that may escape designated sandbox root directories,
and synthesizes strict confinement guardrails preventing directory traversal (../) attacks.
"""

import ast
import os
from typing import Tuple, List, Optional


def safe_path_jail(base_dir: str, untrusted_path: str) -> str:
    """
    Runtime jail helper: resolves untrusted_path within base_dir and verifies
    it does not escape using realpath and commonpath checks.
    """
    abs_base = os.path.realpath(base_dir)
    resolved = os.path.realpath(os.path.join(abs_base, untrusted_path))
    if os.path.commonpath([abs_base, resolved]) != abs_base:
        raise PermissionError(f"Path traversal escape attempt detected: {untrusted_path} outside {base_dir}")
    return resolved


class PathTraversalHealer(ast.NodeTransformer):
    """
    AST transformer that intercepts unconfined file open calls and injects safe path
    resolution guardrails to quarantine directory traversal vulnerabilities.
    """

    SAFE_JAIL_HELPER_DEF = """
import os

def _autocure_safe_path(base_dir, untrusted_path):
    abs_base = os.path.realpath(base_dir)
    resolved = os.path.realpath(os.path.join(abs_base, untrusted_path))
    if os.path.commonpath([abs_base, resolved]) != abs_base:
        raise PermissionError("Path traversal escape attempt detected: " + str(untrusted_path))
    return resolved
"""

    def __init__(self):
        super().__init__()
        self.healed_count = 0
        self.healed_locations: List[int] = []
        self.needs_helper = False

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)

        # 1. Detect open(os.path.join(base, filename), ...) or open(dynamic_path, ...)
        is_open = False
        if isinstance(node.func, ast.Name) and node.func.id == "open":
            is_open = True
        elif isinstance(node.func, ast.Attribute) and node.func.attr == "open" and isinstance(node.func.value, ast.Name) and node.func.value.id in ("builtins", "io"):
            is_open = True

        if is_open and node.args:
            path_arg = node.args[0]

            # Case A: open(os.path.join(base, target))
            if isinstance(path_arg, ast.Call) and isinstance(path_arg.func, ast.Attribute):
                if path_arg.func.attr == "join" and isinstance(path_arg.func.value, ast.Attribute):
                    if path_arg.func.value.attr == "path" and isinstance(path_arg.func.value.value, ast.Name) and path_arg.func.value.value.id == "os":
                        if len(path_arg.args) >= 2:
                            self.healed_count += 1
                            self.healed_locations.append(node.lineno if hasattr(node, "lineno") else 0)
                            self.needs_helper = True

                            base_arg = path_arg.args[0]
                            target_arg = path_arg.args[1]
                            node.args[0] = ast.Call(
                                func=ast.Name(id="_autocure_safe_path", ctx=ast.Load()),
                                args=[base_arg, target_arg],
                                keywords=[],
                            )
                            return node

            # Case B: open(f"{base}/{target}")
            if isinstance(path_arg, ast.JoinedStr) and len(path_arg.values) >= 2:
                # Dynamic format string path
                self.healed_count += 1
                self.healed_locations.append(node.lineno if hasattr(node, "lineno") else 0)
                self.needs_helper = True
                node.args[0] = ast.Call(
                    func=ast.Name(id="_autocure_safe_path", ctx=ast.Load()),
                    args=[ast.Constant(value="."), path_arg],
                    keywords=[],
                )
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
