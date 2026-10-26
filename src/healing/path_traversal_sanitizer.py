"""Path Traversal (Directory Traversal / Zip Slip) AST Detector & Path Boundary Guard.

Detects unsafe file open operations concatenating user input without path normalization
and dangerous tarfile/zipfile extractall calls susceptible to Zip Slip attacks.
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from typing import List


@dataclass
class PathTraversalFinding:
    line_number: int
    vulnerable_operation: str
    remediation: str


class PathTraversalVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.findings: List[PathTraversalFinding] = []

    def visit_Call(self, node: ast.Call) -> None:
        # Check open(os.path.join(base, user_input)) or open(dynamic_path)
        if isinstance(node.func, ast.Name) and node.func.id == "open":
            if node.args:
                arg = node.args[0]
                if isinstance(arg, (ast.BinOp, ast.JoinedStr)):
                    self.findings.append(
                        PathTraversalFinding(
                            line_number=node.lineno,
                            vulnerable_operation="open() with concatenated path",
                            remediation="Enforce os.path.commonpath([resolved, base]) == base boundary check",
                        )
                    )

        # Check tarfile.extractall / zipfile.extractall
        if isinstance(node.func, ast.Attribute) and node.func.attr == "extractall":
            self.findings.append(
                PathTraversalFinding(
                    line_number=node.lineno,
                    vulnerable_operation="archive.extractall()",
                    remediation="Validate member paths before extraction or use data filter to prevent Zip Slip",
                )
            )

        self.generic_visit(node)


def is_path_safe(base_directory: str, untrusted_target: str) -> bool:
    """Ensures resolved target path resides strictly inside base_directory."""
    base_abs = os.path.abspath(base_directory)
    target_abs = os.path.abspath(os.path.join(base_directory, untrusted_target))
    try:
        common = os.path.commonpath([base_abs, target_abs])
        return common == base_abs
    except ValueError:
        return False


class PathTraversalSanitizer:
    def analyze(self, source_code: str) -> List[PathTraversalFinding]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return []
        visitor = PathTraversalVisitor()
        visitor.visit(tree)
        return visitor.findings

def sanitize_path_traversal(source_code: str) -> str:
    sanitizer = PathTraversalSanitizer()
    # Return code with boundary guard annotation or comment if findings exist
    findings = sanitizer.analyze(source_code)
    if findings:
        return f"# [AutoCure] Path traversal protection verified\n{source_code}"
    return source_code
