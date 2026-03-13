"""
Repository Tools for AI Error Analysis
═══════════════════════════════════════

Provides tools the AI can call during error analysis to inspect the
repository when the initial AST-traced context is insufficient.

Tools:
  search_code  – Full-text grep across repository files (keyword / regex)
  dir_tree     – Directory tree listing with configurable depth (max 3)
  read_file    – Read file contents with optional line range
"""

import os
import re
import fnmatch
from pathlib import Path
from typing import List, Dict, Optional

from utils.logger import setup_colored_logger

logger = setup_colored_logger("repo_tools")


# ════════════════════════════════════════════════════════════════
#  Constants
# ════════════════════════════════════════════════════════════════

CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php", ".swift",
    ".kt", ".scala", ".r", ".sql", ".html", ".css", ".scss",
    ".yaml", ".yml", ".json", ".toml", ".cfg", ".ini",
    ".md", ".txt", ".sh", ".bash", ".ps1", ".bat",
    ".dockerfile", ".env.example", ".gitignore",
}

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
    ".egg-info", ".eggs", ".cache", "coverage", ".next", ".nuxt",
    ".idea", ".vscode",
}

MAX_FILE_SIZE = 512 * 1024  # 512 KB


# ════════════════════════════════════════════════════════════════
#  Tool Definitions (OpenAI function-calling schema)
# ════════════════════════════════════════════════════════════════

TOOL_DEFINITIONS: List[Dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": (
                "Search for a keyword, function name, variable, class, or any "
                "text across all files in the repository. Returns matching lines "
                "with file paths, line numbers, and surrounding context. "
                "Use this when you need to find where something is defined, "
                "imported, or called."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Text to search for (case-insensitive). Can be a "
                            "function name, variable, class, import, string, etc."
                        ),
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum results to return (default 10, max 30).",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dir_tree",
            "description": (
                "Show the directory structure of the repository (or a sub-directory) "
                "as a tree. Useful for understanding project layout before reading "
                "specific files."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Relative path of directory to list (default: repo root '.').",
                        "default": ".",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "How many levels deep to show (1-3, default 2).",
                        "default": 2,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read the contents of a specific file in the repository. "
                "Can read the entire file or a specific line range. "
                "Returns numbered lines."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Relative path to the file (e.g. 'src/app.py').",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "First line to read (1-based, default 1).",
                        "default": 1,
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Last line to read (0 = end of file, default 0).",
                        "default": 0,
                    },
                },
                "required": ["file_path"],
            },
        },
    },
]


# ════════════════════════════════════════════════════════════════
#  RepoIndex — lightweight in-memory search index
# ════════════════════════════════════════════════════════════════

class RepoIndex:
    """
    In-memory index for a single repository.
    Caches file contents for fast grep-style search.
    Call invalidate() after a git pull to refresh.
    """

    def __init__(self, repo_path: str):
        self.repo_path = os.path.normpath(repo_path)
        self._files: Dict[str, str] = {}        # rel_path → content
        self._indexed = False

    # ── Indexing ──────────────────────────────────────────────

    def _ensure_indexed(self):
        if self._indexed:
            return
        self._files.clear()
        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in CODE_EXTENSIONS:
                    continue
                abs_path = os.path.join(root, fname)
                try:
                    if os.path.getsize(abs_path) > MAX_FILE_SIZE:
                        continue
                except OSError:
                    continue
                rel = os.path.relpath(abs_path, self.repo_path).replace("\\", "/")
                try:
                    with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                        self._files[rel] = f.read()
                except OSError:
                    pass
        self._indexed = True
        logger.info(f"Indexed {len(self._files)} files in {self.repo_path}")

    def invalidate(self):
        """Mark the index as stale so next access rebuilds it."""
        self._indexed = False

    # ── search_code ──────────────────────────────────────────

    def search(self, query: str, max_results: int = 10) -> List[Dict]:
        """
        Grep for *query* across all indexed files.
        Returns list of {file, line, match, context}.
        """
        self._ensure_indexed()
        max_results = max(1, min(max_results, 30))
        results: List[Dict] = []
        query_lower = query.lower()

        for rel_path, content in self._files.items():
            lines = content.splitlines()
            for i, line in enumerate(lines):
                if query_lower in line.lower():
                    start = max(0, i - 2)
                    end = min(len(lines), i + 3)
                    ctx_lines = []
                    for j in range(start, end):
                        marker = ">>>" if j == i else "   "
                        ctx_lines.append(f"{marker} {j+1:>4} | {lines[j]}")
                    results.append({
                        "file": rel_path,
                        "line": i + 1,
                        "match": line.strip()[:200],
                        "context": "\n".join(ctx_lines),
                    })
                    if len(results) >= max_results:
                        return results
        return results

    # ── dir_tree ─────────────────────────────────────────────

    def dir_tree(self, directory: str = ".", depth: int = 2) -> str:
        """
        Return a tree-formatted directory listing (max depth 3).
        """
        depth = max(1, min(depth, 3))
        base = os.path.normpath(os.path.join(self.repo_path, directory))

        # Safety: ensure base is inside repo
        try:
            Path(base).resolve().relative_to(Path(self.repo_path).resolve())
        except ValueError:
            return f"Error: directory '{directory}' is outside the repository."

        if not os.path.isdir(base):
            return f"Error: directory not found: {directory}"

        lines: List[str] = [f"{directory}/"]
        self._walk_tree(base, depth, lines, prefix="")
        return "\n".join(lines)

    def _walk_tree(self, path: str, depth: int, lines: List[str], prefix: str):
        if depth <= 0:
            return
        try:
            entries = sorted(os.listdir(path))
        except PermissionError:
            return
        entries = [e for e in entries if e not in SKIP_DIRS and not e.startswith(".")]

        dirs = [e for e in entries if os.path.isdir(os.path.join(path, e))]
        files = [e for e in entries if not os.path.isdir(os.path.join(path, e))]
        ordered = dirs + files

        for i, entry in enumerate(ordered):
            is_last = i == len(ordered) - 1
            connector = "└── " if is_last else "├── "
            entry_path = os.path.join(path, entry)
            if os.path.isdir(entry_path):
                lines.append(f"{prefix}{connector}{entry}/")
                extension = "    " if is_last else "│   "
                self._walk_tree(entry_path, depth - 1, lines, prefix + extension)
            else:
                lines.append(f"{prefix}{connector}{entry}")

    # ── read_file ────────────────────────────────────────────

    def read_file(self, file_path: str, start_line: int = 1, end_line: int = 0) -> str:
        """
        Read a file (or section) from the repo.  Returns numbered lines.
        """
        self._ensure_indexed()

        # Normalise path separators
        file_path = file_path.replace("\\", "/")
        content = self._files.get(file_path)

        if content is None:
            abs_path = os.path.join(self.repo_path, file_path)
            if os.path.isfile(abs_path):
                try:
                    with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                except OSError:
                    return f"Error: could not read {file_path}"
            else:
                return f"Error: file not found: {file_path}"

        lines = content.splitlines()
        total = len(lines)
        s = max(1, start_line) - 1
        e = end_line if end_line > 0 else total
        e = min(e, total)

        # Cap output to ~200 lines to control token usage
        if e - s > 200:
            e = s + 200

        result = []
        for idx in range(s, e):
            result.append(f"{idx+1:>4} | {lines[idx]}")
        if e < total:
            result.append(f"  ... ({total - e} more lines)")
        return "\n".join(result)


# ════════════════════════════════════════════════════════════════
#  Tool Execution
# ════════════════════════════════════════════════════════════════

def execute_tool(index: RepoIndex, tool_name: str, args: dict) -> str:
    """
    Execute a named tool against a RepoIndex.
    Returns result as a plain-text string suitable for AI consumption.
    """
    try:
        if tool_name == "search_code":
            hits = index.search(
                query=args.get("query", ""),
                max_results=min(int(args.get("max_results", 10)), 30),
            )
            if not hits:
                return "No results found."
            parts = []
            for h in hits:
                parts.append(f"### {h['file']}:{h['line']}\n{h['context']}")
            return "\n\n".join(parts)

        elif tool_name == "dir_tree":
            return index.dir_tree(
                directory=args.get("directory", "."),
                depth=min(int(args.get("depth", 2)), 3),
            )

        elif tool_name == "read_file":
            return index.read_file(
                file_path=args.get("file_path", ""),
                start_line=int(args.get("start_line", 1)),
                end_line=int(args.get("end_line", 0)),
            )

        return f"Unknown tool: {tool_name}"
    except Exception as exc:
        return f"Tool error ({tool_name}): {exc}"


# ════════════════════════════════════════════════════════════════
#  Singleton cache (one index per repo path)
# ════════════════════════════════════════════════════════════════

_indexes: Dict[str, RepoIndex] = {}


def get_repo_index(repo_path: str) -> RepoIndex:
    """Get or create a RepoIndex for the given path."""
    key = os.path.normpath(repo_path)
    if key not in _indexes:
        _indexes[key] = RepoIndex(repo_path)
    return _indexes[key]


def invalidate_repo_index(repo_path: str):
    """Invalidate cached index after a git pull."""
    key = os.path.normpath(repo_path)
    idx = _indexes.get(key)
    if idx:
        idx.invalidate()
