"""
Minimal-Diff AST Patch Generator (AutoCure Healing Module)
==========================================================
Analyzes tracebacks and generates pinpoint AST edits for common defect patterns:
  a) IndexError -> Insert array bounds check guard
  b) KeyError -> Convert to dict.get(key, default) or membership test guard
  c) AttributeError / NoneType -> Insert null-coalescing guard
  d) ZeroDivisionError -> Insert non-zero divisor guard

Every generated node is strictly validated with ast.parse() before applying to disk.
"""

from __future__ import annotations

import ast
import difflib
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ast_patcher")


class DefectPattern:
    """Supported runtime defect types for surgical AST patching."""
    INDEX_ERROR = "IndexError"
    KEY_ERROR = "KeyError"
    ATTRIBUTE_ERROR = "AttributeError"
    TYPE_ERROR = "TypeError"
    ZERO_DIVISION = "ZeroDivisionError"


@dataclass
class ASTPatch:
    """Represents a minimal-diff AST patch for a specific defect."""
    file_path: str
    line_number: int
    defect_type: str
    original_code: str
    patched_code: str
    diff: str
    node_type: str
    explanation: str
    original_line: str = ""
    patched_line: str = ""
    confidence: float = 0.95
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert patch metadata to dictionary."""
        return {
            "file_path": self.file_path,
            "line_number": self.line_number,
            "defect_type": self.defect_type,
            "diff": self.diff,
            "node_type": self.node_type,
            "explanation": self.explanation,
            "original_line": self.original_line,
            "patched_line": self.patched_line,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


class ASTPatcher:
    """
    Analyzes error tracebacks and applies pinpoint, syntax-validated AST edits.
    """

    def __init__(self, repo_path: str = ""):
        self.repo_path = repo_path or os.getcwd()

    # =========================================================================
    # Public API
    # =========================================================================

    def generate_patch_from_traceback(
        self, traceback_str: str, repo_path: str = ""
    ) -> Optional[ASTPatch]:
        """
        Parse a Python stack traceback and generate a pinpoint AST patch
        for the innermost defect frame.
        """
        root_path = repo_path or self.repo_path
        parsed = self.parse_traceback(traceback_str, root_path)
        if not parsed:
            logger.warning("Could not extract actionable defect frame from traceback.")
            return None

        file_path, line_no, defect_type, error_msg = parsed
        return self.generate_patch(
            file_path=file_path,
            line_number=line_no,
            defect_type=defect_type,
            error_message=error_msg,
            repo_path=root_path,
        )

    def generate_patch(
        self,
        file_path: str,
        line_number: int,
        defect_type: str,
        error_message: str = "",
        repo_path: str = "",
        use_membership_guard: bool = False,
    ) -> Optional[ASTPatch]:
        """
        Generate a minimal-diff AST patch for a targeted file and line number.
        Validates all generated nodes with ast.parse() before returning.
        """
        root_path = repo_path or self.repo_path
        full_path = self._resolve_file_path(file_path, root_path)
        if not full_path or not os.path.isfile(full_path):
            logger.error(f"Target file does not exist: {file_path}")
            return None

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                source_code = f.read()
        except Exception as e:
            logger.error(f"Failed to read target file {full_path}: {e}")
            return None

        try:
            tree = ast.parse(source_code, filename=file_path)
        except SyntaxError as e:
            logger.error(f"Cannot patch file with preexisting SyntaxError in {file_path}: {e}")
            return None

        lines = source_code.splitlines(keepends=True)
        if line_number < 1 or line_number > len(lines):
            logger.error(f"Line {line_number} is out of bounds for {file_path} ({len(lines)} lines)")
            return None

        norm_defect = self._normalize_defect_type(defect_type, error_message)

        # Dispatch to specialized pattern patchers
        patch_info: Optional[Tuple[str, str, str, str]] = None
        if norm_defect == DefectPattern.INDEX_ERROR:
            patch_info = self._patch_index_error(tree, lines, line_number)
        elif norm_defect == DefectPattern.KEY_ERROR:
            patch_info = self._patch_key_error(
                tree, lines, line_number, error_message, use_membership=use_membership_guard
            )
        elif norm_defect in (DefectPattern.ATTRIBUTE_ERROR, DefectPattern.TYPE_ERROR):
            patch_info = self._patch_attribute_or_null_error(
                tree, lines, line_number, error_message
            )
        elif norm_defect == DefectPattern.ZERO_DIVISION:
            patch_info = self._patch_zero_division_error(tree, lines, line_number)

        if not patch_info:
            logger.warning(f"No suitable AST node found at {file_path}:{line_number} for {defect_type}")
            return None

        patched_code, orig_line, patched_line, explanation, node_type = patch_info

        # 1. Validate full patched code with ast.parse()
        try:
            ast.parse(patched_code, filename=file_path)
        except SyntaxError as e:
            logger.error(f"Patched code failed AST syntax validation for {file_path}: {e}")
            return None

        # 2. Build unified diff
        diff_lines = list(
            difflib.unified_diff(
                lines,
                patched_code.splitlines(keepends=True),
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
            )
        )
        diff_text = "".join(diff_lines)

        rel_path = os.path.relpath(full_path, root_path) if root_path else file_path

        return ASTPatch(
            file_path=rel_path,
            line_number=line_number,
            defect_type=defect_type,
            original_code=source_code,
            patched_code=patched_code,
            diff=diff_text,
            node_type=node_type,
            explanation=explanation,
            original_line=orig_line.strip(),
            patched_line=patched_line.strip(),
            confidence=0.95,
            metadata={
                "error_message": error_message,
                "norm_defect": norm_defect,
            },
        )

    def apply_patch(
        self, patch: ASTPatch, repo_path: str = "", backup: bool = True
    ) -> bool:
        """
        Apply patch to disk. Creates backup file '.autocure_bak' if backup=True.
        Validates target file with ast.parse() after writing.
        """
        root_path = repo_path or self.repo_path
        full_path = self._resolve_file_path(patch.file_path, root_path)
        if not full_path:
            return False

        try:
            if backup:
                bak_path = f"{full_path}.autocure_bak"
                with open(full_path, "r", encoding="utf-8") as f:
                    orig_content = f.read()
                with open(bak_path, "w", encoding="utf-8") as f:
                    f.write(orig_content)

            with open(full_path, "w", encoding="utf-8") as f:
                f.write(patch.patched_code)

            # Re-verify on disk
            ast.parse(patch.patched_code, filename=full_path)
            logger.info(f"✓ Applied AST patch cleanly to {full_path}:{patch.line_number}")
            return True
        except Exception as e:
            logger.error(f"Failed to apply patch to {full_path}: {e}")
            self.rollback_patch(patch, repo_path=root_path)
            return False

    def rollback_patch(self, patch: ASTPatch, repo_path: str = "") -> bool:
        """Roll back file changes to original code and remove backup."""
        root_path = repo_path or self.repo_path
        full_path = self._resolve_file_path(patch.file_path, root_path)
        if not full_path:
            return False

        bak_path = f"{full_path}.autocure_bak"
        restored = False

        if os.path.isfile(bak_path):
            try:
                with open(bak_path, "r", encoding="utf-8") as f:
                    content = f.read()
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)
                os.remove(bak_path)
                restored = True
            except Exception as e:
                logger.error(f"Failed restoring from backup {bak_path}: {e}")

        if not restored and patch.original_code:
            try:
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(patch.original_code)
                restored = True
            except Exception as e:
                logger.error(f"Failed restoring original code to {full_path}: {e}")

        if restored:
            logger.info(f"✓ Rolled back patch for {full_path}:{patch.line_number}")
        return restored

    # =========================================================================
    # Pattern Handlers (Strictly Validated with ast.parse)
    # =========================================================================

    def _patch_index_error(
        self, tree: ast.AST, lines: List[str], line_no: int
    ) -> Optional[Tuple[str, str, str, str, str]]:
        """
        Insert an array bounds check guard for IndexError.
        e.g. items[idx] -> (items[idx] if 0 <= idx < len(items) else None)
        """
        candidate_nodes = self._find_nodes_by_type(tree, ast.Subscript, line_no)
        if not candidate_nodes:
            return None

        # Select the target subscript node
        node = candidate_nodes[0]
        val_str = ast.unparse(node.value)
        slice_str = ast.unparse(node.slice)

        # Generate pinpoint replacement
        replacement = f"({val_str}[{slice_str}] if 0 <= {slice_str} < len({val_str}) else None)"

        # Validate replacement node with ast.parse
        ast.parse(replacement, mode="eval")

        patched_code, orig_line, patched_line = self._replace_node_span(
            lines, node, replacement
        )
        explanation = (
            f"Insert array bounds check guard '0 <= {slice_str} < len({val_str})' "
            f"around subscript '{val_str}[{slice_str}]' to prevent IndexError."
        )
        return patched_code, orig_line, patched_line, explanation, "ast.Subscript"

    def _patch_key_error(
        self,
        tree: ast.AST,
        lines: List[str],
        line_no: int,
        error_message: str = "",
        use_membership: bool = False,
    ) -> Optional[Tuple[str, str, str, str, str]]:
        """
        Convert dict[key] to dict.get(key, None) or membership guard for KeyError.
        """
        candidate_nodes = self._find_nodes_by_type(tree, ast.Subscript, line_no)
        if not candidate_nodes:
            return None

        # Filter by key name if mentioned in KeyError message: e.g. KeyError: 'user_id'
        node = candidate_nodes[0]
        if len(candidate_nodes) > 1 and error_message:
            key_match = re.search(r"['\"]([^'\"]+)['\"]", error_message)
            if key_match:
                k_val = key_match.group(1)
                for cand in candidate_nodes:
                    if ast.unparse(cand.slice).strip("'\"") == k_val:
                        node = cand
                        break

        dict_str = ast.unparse(node.value)
        key_str = ast.unparse(node.slice)

        if use_membership:
            replacement = f"({dict_str}[{key_str}] if {key_str} in {dict_str} else None)"
            explanation = f"Insert membership test '{key_str} in {dict_str}' to guard dict lookup."
        else:
            replacement = f"{dict_str}.get({key_str}, None)"
            explanation = f"Convert subscript '{dict_str}[{key_str}]' to safe lookup '{dict_str}.get({key_str}, None)'."

        # Validate replacement node with ast.parse
        ast.parse(replacement, mode="eval")

        patched_code, orig_line, patched_line = self._replace_node_span(
            lines, node, replacement
        )
        return patched_code, orig_line, patched_line, explanation, "ast.Subscript"

    def _patch_attribute_or_null_error(
        self, tree: ast.AST, lines: List[str], line_no: int, error_message: str = ""
    ) -> Optional[Tuple[str, str, str, str, str]]:
        """
        Insert null-coalescing guard for AttributeError or 'NoneType' errors.
        e.g. user.profile -> (user.profile if user is not None else None)
        """
        # 1. Attribute access on None: 'NoneType' object has no attribute 'attr'
        attr_nodes = self._find_nodes_by_type(tree, ast.Attribute, line_no)
        target_attr = None
        if error_message:
            m = re.search(r"has no attribute ['\"]([^'\"]+)['\"]", error_message)
            if m:
                target_attr = m.group(1)

        if attr_nodes:
            node = attr_nodes[0]
            if target_attr:
                for a in attr_nodes:
                    if a.attr == target_attr:
                        node = a
                        break

            target_str = ast.unparse(node)
            val_str = ast.unparse(node.value)
            replacement = f"({target_str} if {val_str} is not None else None)"

            # Validate replacement node with ast.parse
            ast.parse(replacement, mode="eval")

            patched_code, orig_line, patched_line = self._replace_node_span(
                lines, node, replacement
            )
            explanation = (
                f"Insert null-coalescing guard 'if {val_str} is not None' "
                f"protecting attribute access '{target_str}'."
            )
            return patched_code, orig_line, patched_line, explanation, "ast.Attribute"

        # 2. NoneType subscriptable: 'NoneType' object is not subscriptable
        sub_nodes = self._find_nodes_by_type(tree, ast.Subscript, line_no)
        if sub_nodes:
            snode = sub_nodes[0]
            val_str = ast.unparse(snode.value)
            slice_str = ast.unparse(snode.slice)
            replacement = f"({val_str}[{slice_str}] if {val_str} is not None else None)"
            ast.parse(replacement, mode="eval")
            patched_code, orig_line, patched_line = self._replace_node_span(
                lines, snode, replacement
            )
            explanation = f"Insert null-check guard '{val_str} is not None' before subscript."
            return patched_code, orig_line, patched_line, explanation, "ast.Subscript"

        return None

    def _patch_zero_division_error(
        self, tree: ast.AST, lines: List[str], line_no: int
    ) -> Optional[Tuple[str, str, str, str, str]]:
        """
        Insert non-zero divisor guard for ZeroDivisionError.
        e.g. a / b -> (a / b if b != 0 else 0)
        """
        binop_nodes = self._find_nodes_by_type(tree, ast.BinOp, line_no)
        div_nodes = [b for b in binop_nodes if isinstance(b.op, (ast.Div, ast.FloorDiv, ast.Mod))]
        if not div_nodes:
            return None

        node = div_nodes[0]
        left_str = ast.unparse(node.left)
        right_str = ast.unparse(node.right)
        op_symbol = "/" if isinstance(node.op, ast.Div) else ("//" if isinstance(node.op, ast.FloorDiv) else "%")

        replacement = f"({left_str} {op_symbol} {right_str} if {right_str} != 0 else 0)"
        ast.parse(replacement, mode="eval")

        patched_code, orig_line, patched_line = self._replace_node_span(
            lines, node, replacement
        )
        explanation = f"Insert non-zero divisor guard '{right_str} != 0' to prevent ZeroDivisionError."
        return patched_code, orig_line, patched_line, explanation, "ast.BinOp"

    # =========================================================================
    # Helpers
    # =========================================================================

    @staticmethod
    def parse_traceback(
        traceback_str: str, repo_path: str = ""
    ) -> Optional[Tuple[str, int, str, str]]:
        """
        Extract (file_path, line_number, defect_type, error_message)
        from a Python stack traceback or pytest failure output.
        """
        if not traceback_str or not traceback_str.strip():
            return None

        lines = [l.strip() for l in traceback_str.strip().splitlines() if l.strip()]
        if not lines:
            return None

        # 1. Parse Exception type and message
        defect_type = "UnknownError"
        error_msg = ""
        err_search = re.search(
            r"(?:^|\n)\s*(?:E\s+|FAILED\s+.*-\s+)?([a-zA-Z_]\w*Error|[a-zA-Z_]\w*Exception):\s*(.*)",
            traceback_str,
        )
        if err_search:
            defect_type = err_search.group(1).strip()
            error_msg = err_search.group(2).strip()
        else:
            for l in reversed(lines):
                m = re.match(r"^([a-zA-Z_]\w*Error|[a-zA-Z_]\w*Exception):\s*(.*)$", l)
                if m:
                    defect_type = m.group(1).strip()
                    error_msg = m.group(2).strip()
                    break

        # 2. Extract frames (standard Python tracebacks and pytest formats)
        raw_frames: List[Tuple[str, int]] = []
        for m in re.finditer(r'File\s+["\']([^"\']+)["\']\s*,\s*line\s+(\d+)', traceback_str):
            raw_frames.append((m.group(1), int(m.group(2))))

        for m in re.finditer(r'(?:^|\n)\s*([a-zA-Z0-9_./\\-]+\.py):(\d+):', traceback_str):
            raw_frames.append((m.group(1), int(m.group(2))))

        if not raw_frames:
            return None

        # Prefer non-test application files over test files if available
        non_test_frames = [
            f for f in raw_frames if not os.path.basename(f[0]).startswith("test_")
        ]
        frames_to_try = non_test_frames if non_test_frames else raw_frames

        for raw_path, line_no in reversed(frames_to_try):
            raw_path_norm = raw_path.replace("\\", "/")
            if repo_path:
                norm_repo = os.path.normpath(repo_path).replace("\\", "/")
                if os.path.isabs(raw_path_norm) and raw_path_norm.startswith(norm_repo):
                    rel = os.path.relpath(raw_path, repo_path)
                    return rel, line_no, defect_type, error_msg
                candidate = os.path.join(repo_path, raw_path)
                if os.path.isfile(candidate):
                    return raw_path, line_no, defect_type, error_msg
                # Check basename match in repo
                base_cand = os.path.basename(raw_path)
                for r, _, fnames in os.walk(repo_path):
                    if base_cand in fnames:
                        rel = os.path.relpath(os.path.join(r, base_cand), repo_path)
                        return rel, line_no, defect_type, error_msg
            else:
                if os.path.isfile(raw_path):
                    return raw_path, line_no, defect_type, error_msg

        # Fallback to last frame
        last_frame = frames_to_try[-1]
        return last_frame[0], last_frame[1], defect_type, error_msg

    def _find_nodes_by_type(
        self, tree: ast.AST, node_cls: type, line_no: int
    ) -> List[ast.AST]:
        """Find AST nodes of node_cls located on or adjacent to line_no."""
        exact_matches = []
        near_matches = []

        for node in ast.walk(tree):
            if isinstance(node, node_cls) and hasattr(node, "lineno"):
                if node.lineno == line_no:
                    exact_matches.append(node)
                elif abs(node.lineno - line_no) <= 1:
                    near_matches.append(node)

        # Prefer deepest (most specific) expression if multiple exist on the line
        matches = exact_matches if exact_matches else near_matches
        matches.sort(
            key=lambda n: (getattr(n, "end_col_offset", 0) - getattr(n, "col_offset", 0)),
            reverse=True,
        )
        return matches

    def _replace_node_span(
        self, lines: List[str], node: ast.AST, replacement: str
    ) -> Tuple[str, str, str]:
        """Surgically replace the exact text span of an AST node in lines."""
        line_idx = node.lineno - 1
        orig_line = lines[line_idx]

        col_start = getattr(node, "col_offset", None)
        col_end = getattr(node, "end_col_offset", None)

        if col_start is not None and col_end is not None and col_start < col_end:
            # Single-line surgical replacement
            patched_line = orig_line[:col_start] + replacement + orig_line[col_end:]
        else:
            # Fallback line substitution
            patched_line = replacement + "\n"

        patched_lines = list(lines)
        patched_lines[line_idx] = patched_line
        patched_code = "".join(patched_lines)
        return patched_code, orig_line, patched_line

    def _resolve_file_path(self, file_path: str, repo_path: str) -> Optional[str]:
        """Resolve a relative or absolute file path within repo_path."""
        if os.path.isabs(file_path) and os.path.isfile(file_path):
            return os.path.normpath(file_path)
        if repo_path:
            full = os.path.join(repo_path, file_path)
            if os.path.isfile(full):
                return os.path.normpath(full)
            # Try searching for filename inside repo
            target_name = os.path.basename(file_path)
            for root, _, files in os.walk(repo_path):
                if target_name in files:
                    return os.path.normpath(os.path.join(root, target_name))
        if os.path.isfile(file_path):
            return os.path.normpath(file_path)
        return None

    @staticmethod
    def _normalize_defect_type(defect_type: str, message: str = "") -> str:
        """Map raw error name or message heuristics to DefectPattern."""
        dt = defect_type.strip()
        msg = message.lower()
        if "IndexError" in dt or "out of range" in msg:
            return DefectPattern.INDEX_ERROR
        if "KeyError" in dt:
            return DefectPattern.KEY_ERROR
        if "AttributeError" in dt or "has no attribute" in msg:
            return DefectPattern.ATTRIBUTE_ERROR
        if "ZeroDivision" in dt or "division by zero" in msg:
            return DefectPattern.ZERO_DIVISION
        if "TypeError" in dt and "nonetype" in msg:
            if "subscriptable" in msg:
                return DefectPattern.TYPE_ERROR
            return DefectPattern.ATTRIBUTE_ERROR
        return dt
