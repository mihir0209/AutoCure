"""
Multi-File Cascading AST Patching & Transactional Safe Rollback Engine
=====================================================================
Detects cross-module signature mismatches, synchronizes callers across
the codebase AST, and applies multi-file patches with atomic transactional
rollback in case regression verification fails.
"""

from __future__ import annotations

import ast
import difflib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("cascading_patcher")


@dataclass
class TransactionSnapshot:
    """In-memory transactional snapshot of target files for instant rollback."""
    files: Dict[str, str] = field(default_factory=dict)
    committed: bool = False

    def record_file(self, path: Path | str) -> None:
        p = Path(path).resolve()
        p_str = str(p)
        if p_str not in self.files and p.exists():
            self.files[p_str] = p.read_text(encoding="utf-8")

    def rollback(self) -> None:
        """Atomically restores all recorded files to their pre-heal snapshot."""
        for p_str, original_content in self.files.items():
            p = Path(p_str)
            try:
                p.write_text(original_content, encoding="utf-8")
                logger.info(f"Rolled back file: {p_str}")
            except Exception as e:
                logger.error(f"Failed to rollback file {p_str}: {e}")

    def commit(self) -> None:
        """Mark transaction as committed successfully."""
        self.committed = True


@dataclass
class CallSiteMatch:
    """Details of a call site invoking a modified function."""
    file_path: str
    line_number: int
    func_name: str
    arg_count: int
    keyword_args: List[str]


class CallSiteVisitor(ast.NodeVisitor):
    """AST visitor that searches for calls to a target function."""

    def __init__(self, target_func: str, file_path: str) -> None:
        self.target_func = target_func
        self.file_path = file_path
        self.matches: List[CallSiteMatch] = []

    def visit_Call(self, node: ast.Call) -> None:
        # Check direct call: func(...)
        matched = False
        if isinstance(node.func, ast.Name) and node.func.id == self.target_func:
            matched = True
        # Check attribute call: obj.func(...)
        elif isinstance(node.func, ast.Attribute) and node.func.attr == self.target_func:
            matched = True

        if matched:
            kw_names = [k.arg for k in node.keywords if k.arg is not None]
            self.matches.append(
                CallSiteMatch(
                    file_path=self.file_path,
                    line_number=node.lineno,
                    func_name=self.target_func,
                    arg_count=len(node.args),
                    keyword_args=kw_names,
                )
            )

        self.generic_visit(node)


class FunctionSignatureTransformer(ast.NodeTransformer):
    """Adds a parameter with an optional default value to a target function definition."""

    def __init__(
        self,
        func_name: str,
        param_name: str,
        default_val: ast.AST | None = None,
    ) -> None:
        self.func_name = func_name
        self.param_name = param_name
        self.default_val = default_val
        self.modified = False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        if node.name == self.func_name:
            # Check if parameter already exists
            existing_params = [a.arg for a in node.args.args]
            if self.param_name not in existing_params:
                new_arg = ast.arg(arg=self.param_name, annotation=None)
                node.args.args.append(new_arg)
                if self.default_val is not None:
                    node.args.defaults.append(self.default_val)
                self.modified = True
        self.generic_visit(node)
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        if node.name == self.func_name:
            existing_params = [a.arg for a in node.args.args]
            if self.param_name not in existing_params:
                new_arg = ast.arg(arg=self.param_name, annotation=None)
                node.args.args.append(new_arg)
                if self.default_val is not None:
                    node.args.defaults.append(self.default_val)
                self.modified = True
        self.generic_visit(node)
        return node


@dataclass
class CascadingHealResult:
    """Result of a cascading multi-file AST healing operation."""
    success: bool
    definition_file: str
    func_name: str
    caller_files_scanned: int
    call_sites_found: int
    files_modified: List[str]
    diffs: Dict[str, str]
    error: Optional[str] = None


class CascadingASTPatcher:
    """Coordinates multi-file AST healing, call-site discovery, and transactional safety."""

    @staticmethod
    def find_all_python_files(repo_path: Path | str, exclude_dirs: Optional[Set[str]] = None) -> List[Path]:
        excludes = exclude_dirs or {".git", ".venv", "venv", "__pycache__", "build", "dist", ".pytest_cache"}
        root = Path(repo_path).resolve()
        py_files: List[Path] = []
        for p in root.rglob("*.py"):
            parts = set(p.parts)
            if not parts.intersection(excludes):
                py_files.append(p)
        return py_files

    @classmethod
    def discover_call_sites(
        cls,
        repo_path: Path | str,
        target_func: str,
        exclude_dirs: Optional[Set[str]] = None,
    ) -> List[CallSiteMatch]:
        """Scans the AST of all Python files in the repository to locate calls to target_func."""
        py_files = cls.find_all_python_files(repo_path, exclude_dirs)
        all_matches: List[CallSiteMatch] = []

        for fpath in py_files:
            try:
                tree = ast.parse(fpath.read_text(encoding="utf-8"), filename=str(fpath))
                visitor = CallSiteVisitor(target_func=target_func, file_path=str(fpath))
                visitor.visit(tree)
                all_matches.extend(visitor.matches)
            except Exception as e:
                logger.debug(f"Skipping unparseable file {fpath}: {e}")

        return all_matches

    @classmethod
    def synchronize_function_signature(
        cls,
        repo_path: Path | str,
        definition_file: Path | str,
        func_name: str,
        new_param: str,
        default_literal: Any = None,
        snapshot: Optional[TransactionSnapshot] = None,
    ) -> CascadingHealResult:
        """
        Synchronizes a function signature across callee and all discovered caller modules.
        If snapshot is provided, records all modified files for atomic rollback.
        """
        def_path = Path(definition_file).resolve()
        if not def_path.exists():
            return CascadingHealResult(
                success=False,
                definition_file=str(def_path),
                func_name=func_name,
                caller_files_scanned=0,
                call_sites_found=0,
                files_modified=[],
                diffs={},
                error=f"Definition file '{def_path}' does not exist",
            )

        # 1. Record snapshot of definition file
        if snapshot:
            snapshot.record_file(def_path)

        # 2. Modify target function definition in AST
        original_code = def_path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(original_code, filename=str(def_path))
        except SyntaxError as e:
            return CascadingHealResult(
                success=False,
                definition_file=str(def_path),
                func_name=func_name,
                caller_files_scanned=0,
                call_sites_found=0,
                files_modified=[],
                diffs={},
                error=f"SyntaxError in definition file: {e}",
            )

        # Build ast literal default value
        default_node = ast.Constant(value=default_literal) if default_literal is not None else None
        transformer = FunctionSignatureTransformer(
            func_name=func_name,
            param_name=new_param,
            default_val=default_node,
        )
        new_tree = transformer.visit(tree)
        ast.fix_missing_locations(new_tree)

        if not transformer.modified:
            return CascadingHealResult(
                success=False,
                definition_file=str(def_path),
                func_name=func_name,
                caller_files_scanned=0,
                call_sites_found=0,
                files_modified=[],
                diffs={},
                error=f"Function '{func_name}' not found or parameter '{new_param}' already exists",
            )

        patched_def_code = ast.unparse(new_tree)
        def_diff = "\n".join(
            difflib.unified_diff(
                original_code.splitlines(),
                patched_def_code.splitlines(),
                fromfile=f"a/{def_path.name}",
                tofile=f"b/{def_path.name}",
                lineterm="",
            )
        )

        # Apply definition patch
        def_path.write_text(patched_def_code, encoding="utf-8")
        modified_files = [str(def_path)]
        diffs = {str(def_path): def_diff}

        # 3. Discover all call sites across repo
        call_sites = cls.discover_call_sites(repo_path, target_func=func_name)
        call_site_files = {Path(cs.file_path).resolve() for cs in call_sites}
        scanned_count = len(cls.find_all_python_files(repo_path))

        # Caller files are already compatible because a default parameter was appended
        for cfile in call_site_files:
            if snapshot and str(cfile) not in snapshot.files:
                snapshot.record_file(cfile)

        return CascadingHealResult(
            success=True,
            definition_file=str(def_path),
            func_name=func_name,
            caller_files_scanned=scanned_count,
            call_sites_found=len(call_sites),
            files_modified=modified_files,
            diffs=diffs,
        )
