"""
AST review service for code-review pipelines.

Builds old/new AST views for changed files, compares symbol-level structure,
and traces cross-file references to estimate whether changes are redundant
or likely useful.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.ast_service import get_ast_service
from utils.logger import setup_colored_logger

logger = setup_colored_logger("ast_review_service")

_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", "target", ".next", ".cache",
}


class ASTReviewService:
    """Compare AST old/new trees and derive reference-based insights."""

    def __init__(self):
        self.ast_service = get_ast_service()

    def analyze_review_diff(
        self,
        pr_diff: Dict[str, Any],
        repo_path: str = "",
        base_ref: str = "",
        head_ref: str = "",
    ) -> Dict[str, Any]:
        files = pr_diff.get("files", []) or []
        if not repo_path or not files:
            return {}

        repo_root = Path(repo_path)
        ast_diffs: List[Dict[str, Any]] = []
        changed_symbols: List[Dict[str, Any]] = []

        for f in files:
            file_path = f.get("filename", "")
            if not file_path:
                continue
            if file_path.startswith("visualizer/") or "/visualizer/" in file_path.replace("\\", "/"):
                continue

            lang = self.ast_service.detect_language(file_path)
            if not lang:
                continue

            old_code = self._read_at_ref(repo_root, file_path, base_ref)
            new_code = self._read_at_ref(repo_root, file_path, head_ref)
            if new_code is None:
                new_code = self._read_working_file(repo_root, file_path)

            if old_code is None and new_code is None:
                continue

            file_diff = self._compare_file(file_path, lang, old_code or "", new_code or "")
            if not file_diff:
                continue

            ast_diffs.append(file_diff)
            for sym in file_diff.get("changed_symbols", []):
                changed_symbols.append({
                    "symbol": sym,
                    "file_path": file_path,
                    "change_type": "modified",
                })
            for sym in file_diff.get("added_symbols", []):
                changed_symbols.append({
                    "symbol": sym,
                    "file_path": file_path,
                    "change_type": "added",
                })

        reference_traces = self._trace_references(repo_root, changed_symbols)
        manual_flags = self._build_manual_flags(ast_diffs, reference_traces)
        summary = self._build_summary(ast_diffs, reference_traces, manual_flags)

        return {
            "summary": summary,
            "ast_diffs": ast_diffs,
            "reference_traces": reference_traces,
            "manual_flags": manual_flags,
        }

    def _compare_file(
        self,
        file_path: str,
        language: str,
        old_code: str,
        new_code: str,
    ) -> Dict[str, Any]:
        old_root = self.ast_service.parse_code(old_code, language, file_path) if old_code else None
        new_root = self.ast_service.parse_code(new_code, language, file_path) if new_code else None
        if not old_root and not new_root:
            return {}

        old_symbols = self._extract_symbols(old_root, old_code)
        new_symbols = self._extract_symbols(new_root, new_code)
        old_names = set(old_symbols.keys())
        new_names = set(new_symbols.keys())

        added = sorted(new_names - old_names)
        removed = sorted(old_names - new_names)
        changed = sorted(
            name for name in (old_names & new_names)
            if old_symbols[name].get("body_fingerprint") != new_symbols[name].get("body_fingerprint")
        )

        redundancy_candidates = []
        for symbol in added + changed:
            new_fp = new_symbols.get(symbol, {}).get("body_fingerprint", "")
            if not new_fp:
                continue
            dup_match = self._find_duplicate_fingerprint(new_fp, new_symbols, symbol)
            if dup_match:
                redundancy_candidates.append({
                    "symbol": symbol,
                    "matched_symbol": dup_match,
                    "reason": "Equivalent implementation already exists in new tree",
                })

        return {
            "file_path": file_path,
            "language": language,
            "added_symbols": added,
            "removed_symbols": removed,
            "changed_symbols": changed,
            "redundancy_candidates": redundancy_candidates,
        }

    @staticmethod
    def _find_duplicate_fingerprint(
        fingerprint: str,
        symbols: Dict[str, Dict[str, Any]],
        exclude: str,
    ) -> Optional[str]:
        for name, info in symbols.items():
            if name == exclude:
                continue
            if info.get("body_fingerprint") == fingerprint and fingerprint:
                return name
        return None

    def _extract_symbols(self, root, source_code: str) -> Dict[str, Dict[str, Any]]:
        if not root or not source_code:
            return {}
        lines = source_code.splitlines()
        symbols: Dict[str, Dict[str, Any]] = {}

        def walk(node):
            ntype = (node.node_type or "").lower()
            name = (node.name or "").strip()
            is_symbol = any(k in ntype for k in ("function", "method", "class", "lambda"))
            if is_symbol and name:
                start = max(1, node.start_line)
                end = min(len(lines), max(node.end_line, node.start_line))
                snippet = "\n".join(lines[start - 1:end])
                symbols[name] = {
                    "node_type": ntype,
                    "start_line": node.start_line,
                    "end_line": node.end_line,
                    "body_fingerprint": self._fingerprint(snippet),
                }
            for child in node.children:
                walk(child)

        walk(root)
        return symbols

    @staticmethod
    def _fingerprint(code: str) -> str:
        normalized = re.sub(r"\s+", "", code or "")
        return normalized[:5000]

    def _trace_references(
        self,
        repo_root: Path,
        changed_symbols: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not changed_symbols:
            return []

        symbols = sorted({c["symbol"] for c in changed_symbols if c.get("symbol")})
        traces: List[Dict[str, Any]] = []
        for symbol in symbols:
            patt = re.compile(rf"\b{re.escape(symbol)}\b")
            occurrences: List[Dict[str, Any]] = []
            total_hits = 0

            for file_path in self._iter_source_files(repo_root):
                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                line_hits = []
                for i, line in enumerate(content.splitlines(), 1):
                    if patt.search(line):
                        line_hits.append(i)
                        total_hits += 1
                        if len(line_hits) >= 8:
                            break
                if line_hits:
                    rel = str(file_path.relative_to(repo_root)).replace("\\", "/")
                    occurrences.append({
                        "file_path": rel,
                        "line_numbers": line_hits,
                        "count": len(line_hits),
                    })
                if len(occurrences) >= 20:
                    break

            traces.append({
                "symbol": symbol,
                "total_references": total_hits,
                "occurrences": occurrences,
            })
        return traces

    def _iter_source_files(self, repo_root: Path):
        supported_exts = set(self.ast_service.get_supported_extensions())
        for root, dirs, files in os.walk(repo_root):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]
            for name in files:
                ext = Path(name).suffix.lower()
                if ext in supported_exts:
                    yield Path(root) / name

    @staticmethod
    def _build_manual_flags(
        ast_diffs: List[Dict[str, Any]],
        reference_traces: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        ref_map = {r["symbol"]: r for r in reference_traces}
        flags: List[Dict[str, Any]] = []
        for diff in ast_diffs:
            for red in diff.get("redundancy_candidates", []):
                symbol = red.get("symbol", "")
                refs = ref_map.get(symbol, {}).get("total_references", 0)
                if refs <= 1:
                    flags.append({
                        "file_path": diff.get("file_path", ""),
                        "symbol": symbol,
                        "flag_type": "possible_redundant_change",
                        "reason": f"{red.get('reason', 'Potential redundancy')} and only {refs} reference(s) found",
                    })
        return flags

    @staticmethod
    def _build_summary(
        ast_diffs: List[Dict[str, Any]],
        reference_traces: List[Dict[str, Any]],
        manual_flags: List[Dict[str, Any]],
    ) -> str:
        files = len(ast_diffs)
        changed = sum(len(d.get("changed_symbols", [])) for d in ast_diffs)
        added = sum(len(d.get("added_symbols", [])) for d in ast_diffs)
        refs = sum(r.get("total_references", 0) for r in reference_traces)
        return (
            f"AST compared across {files} file(s); changed symbols={changed}, "
            f"added symbols={added}, traced references={refs}, manual flags={len(manual_flags)}."
        )

    @staticmethod
    def _read_working_file(repo_root: Path, file_path: str) -> Optional[str]:
        full = repo_root / file_path
        if not full.exists():
            return None
        try:
            return full.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None

    def _read_at_ref(self, repo_root: Path, file_path: str, ref: str) -> Optional[str]:
        if not ref:
            return None
        candidates = [ref]
        if "/" not in ref and not re.fullmatch(r"[0-9a-f]{7,40}", ref):
            candidates.append(f"origin/{ref}")
        for cand in candidates:
            out = self._run_git(repo_root, ["show", f"{cand}:{file_path}"])
            if out is not None:
                return out
        return None

    @staticmethod
    def _run_git(repo_root: Path, args: List[str]) -> Optional[str]:
        try:
            proc = subprocess.run(
                ["git", *args],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode == 0:
                return proc.stdout
        except Exception as e:
            logger.debug(f"git {' '.join(args)} failed: {e}")
        return None


_ast_review_service: Optional[ASTReviewService] = None


def get_ast_review_service() -> ASTReviewService:
    global _ast_review_service
    if _ast_review_service is None:
        _ast_review_service = ASTReviewService()
    return _ast_review_service
