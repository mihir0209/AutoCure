"""
AST Service for the Self-Healing Software System v2.0

Provides AST (Abstract Syntax Tree) building and analysis using tree-sitter
with compiled language grammars for multi-language support.

Used for:
- Building AST from source code files (30+ languages via tree-sitter)
- Tracing error locations to specific AST nodes
- Extracting context around error nodes (parent functions, classes, etc.)
- Cross-file import/export reference resolution
- Symbol table extraction for codebase understanding
- Generating interactive AST visualizations for emails and dashboard
"""

import os
import re
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from dataclasses import dataclass, field as dc_field

from utils.models import ASTNode, ASTContext, ASTVisualization
from utils.logger import setup_colored_logger

logger = setup_colored_logger("ast_service")

# ---------------------------------------------------------------------------
# Try to import tree-sitter  (Python bindings >= 0.21)
# ---------------------------------------------------------------------------
TREE_SITTER_AVAILABLE = False
TS_LANGUAGES_AVAILABLE = False
_ts_parsers: Dict[str, Any] = {}   # lang -> parser
_ts_languages: Dict[str, Any] = {} # lang -> Language object

try:
    from tree_sitter import Language, Parser as TSParser
    TREE_SITTER_AVAILABLE = True
except ImportError:
    logger.warning("tree-sitter not installed. pip install tree-sitter tree-sitter-languages")

# Try the pre-built multi-language pack
try:
    import tree_sitter_languages
    TS_LANGUAGES_AVAILABLE = True
except ImportError:
    pass

# ---------------------------------------------------------------------------
# File extension -> language name mapping
# ---------------------------------------------------------------------------
EXTENSION_TO_LANGUAGE: Dict[str, str] = {
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "tsx",
    ".py": "python", ".pyw": "python",
    ".java": "java", ".kt": "kotlin", ".kts": "kotlin", ".scala": "scala",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hh": "cpp",
    ".cs": "c_sharp",
    ".go": "go",
    ".rs": "rust",
    ".html": "html", ".htm": "html",
    ".css": "css",
    ".json": "json",
    ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml",
    ".rb": "ruby",
    ".php": "php",
    ".lua": "lua",
    ".sh": "bash", ".bash": "bash", ".zsh": "bash",
    ".swift": "swift",
    ".ex": "elixir", ".exs": "elixir",
    ".elm": "elm",
    ".ml": "ocaml", ".mli": "ocaml",
    ".sol": "solidity",
    ".zig": "zig",
    ".dart": "dart",
    ".r": "r", ".R": "r",
    ".sql": "sql",
}

LANGUAGE_DISPLAY: Dict[str, str] = {
    "javascript": "JavaScript", "typescript": "TypeScript", "tsx": "TypeScript (TSX)",
    "python": "Python", "java": "Java", "kotlin": "Kotlin", "scala": "Scala",
    "c": "C", "cpp": "C++", "c_sharp": "C#", "go": "Go", "rust": "Rust",
    "html": "HTML", "css": "CSS", "json": "JSON", "yaml": "YAML", "toml": "TOML",
    "ruby": "Ruby", "php": "PHP", "lua": "Lua", "bash": "Bash", "swift": "Swift",
    "elixir": "Elixir", "elm": "Elm", "ocaml": "OCaml", "solidity": "Solidity",
    "zig": "Zig", "dart": "Dart", "r": "R", "sql": "SQL",
}


# ============================================================================
# AST Service
# ============================================================================

class ASTService:
    """
    Service for building and analysing ASTs using tree-sitter.

    Supports 30+ languages via pre-compiled tree-sitter-languages package
    or individually installed tree-sitter-<lang> packages.
    Falls back to regex-based extraction when tree-sitter is unavailable.
    """

    def __init__(self, languages_path: Optional[Path] = None):
        self._parsers: Dict[str, Any] = {}
        self._languages: Dict[str, Any] = {}
        self.languages_path = languages_path

        if TREE_SITTER_AVAILABLE:
            self._initialize_parsers()
        else:
            logger.warning("AST parsing limited – install tree-sitter for full functionality")

    # ------------------------------------------------------------------
    # Initialisation – load tree-sitter language grammars
    # ------------------------------------------------------------------

    def _initialize_parsers(self):
        """Initialize tree-sitter parsers for supported languages."""
        if TS_LANGUAGES_AVAILABLE:
            # tree-sitter-languages bundles grammars for many languages
            for lang_name in LANGUAGE_DISPLAY:
                try:
                    language = tree_sitter_languages.get_language(lang_name)
                    parser = tree_sitter_languages.get_parser(lang_name)
                    self._languages[lang_name] = language
                    self._parsers[lang_name] = parser
                except Exception:
                    pass  # grammar not in bundle
            loaded = list(self._parsers.keys())
            logger.info(f"tree-sitter ready with {len(loaded)} languages via tree-sitter-languages")
        else:
            # Try individual tree-sitter-<lang> packages (pip install tree-sitter-python etc.)
            for lang_name in ("python", "javascript", "typescript", "java", "go", "rust", "c", "cpp"):
                try:
                    mod = __import__(f"tree_sitter_{lang_name}")
                    language = Language(mod.language())
                    parser = TSParser(language)
                    self._languages[lang_name] = language
                    self._parsers[lang_name] = parser
                except Exception:
                    pass
            if self._parsers:
                logger.info(f"tree-sitter ready with individual packages: {list(self._parsers.keys())}")
            else:
                logger.warning("No tree-sitter language grammars found – using regex fallback")

    def _get_parser(self, language: str):
        """Return (parser, language_obj) for a given language name."""
        if language in self._parsers:
            return self._parsers[language], self._languages.get(language)
        # Lazy-load if tree-sitter-languages available
        if TS_LANGUAGES_AVAILABLE:
            try:
                lang_obj = tree_sitter_languages.get_language(language)
                parser = tree_sitter_languages.get_parser(language)
                self._languages[language] = lang_obj
                self._parsers[language] = parser
                return parser, lang_obj
            except Exception:
                pass
        return None, None

    # ------------------------------------------------------------------
    # Language detection
    # ------------------------------------------------------------------

    def detect_language(self, file_path: str) -> Optional[str]:
        """Detect language from file extension."""
        ext = Path(file_path).suffix.lower()
        return EXTENSION_TO_LANGUAGE.get(ext)

    def get_language_name(self, lang_key: str) -> str:
        return LANGUAGE_DISPLAY.get(lang_key, lang_key)

    def get_supported_extensions(self) -> List[str]:
        return list(EXTENSION_TO_LANGUAGE.keys())

    def is_supported(self, file_path: str) -> bool:
        return self.detect_language(file_path) is not None

    # ------------------------------------------------------------------
    # Parsing (public API)
    # ------------------------------------------------------------------

    def parse_file(self, file_path: str) -> Optional[ASTNode]:
        """Parse a source file and return its AST root node."""
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return None
        language = self.detect_language(file_path)
        if not language:
            logger.warning(f"Unsupported language for: {file_path}")
            return None
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                source_code = f.read()
            return self.parse_code(source_code, language, file_path)
        except Exception as e:
            logger.error(f"Error parsing {file_path}: {e}")
            return None

    def parse_code(
        self, source_code: str, language: str, file_path: Optional[str] = None
    ) -> Optional[ASTNode]:
        """Parse source code and return its AST root node."""
        parser, _ = self._get_parser(language)
        if parser is not None:
            return self._parse_tree_sitter(parser, source_code, language, file_path)
        return self._parse_fallback(source_code, language, file_path)

    # ------------------------------------------------------------------
    # tree-sitter parsing
    # ------------------------------------------------------------------

    def _parse_tree_sitter(
        self, parser, source_code: str, language: str, file_path: Optional[str]
    ) -> Optional[ASTNode]:
        """Build ASTNode tree from tree-sitter parse tree."""
        try:
            tree = parser.parse(source_code.encode("utf-8"))
            root = tree.root_node
            return self._ts_node_to_ast(root, source_code, file_path or "unknown", depth=0)
        except Exception as e:
            logger.error(f"tree-sitter parse error: {e}")
            return self._parse_fallback(source_code, language, file_path)

    def _ts_node_to_ast(
        self, node, source_code: str, file_path: str,
        depth: int = 0, max_depth: int = 20
    ) -> ASTNode:
        """Recursively convert a tree-sitter node to our ASTNode model."""
        if depth > max_depth:
            return ASTNode(
                node_id=f"{node.type}_{node.start_point[0]}_{node.start_point[1]}",
                node_type=node.type,
                name="...",
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                start_col=node.start_point[1],
                end_col=node.end_point[1],
            )

        name = self._extract_node_name(node, source_code)

        # Collect named children (skip anonymous punctuation)
        children: List[ASTNode] = []
        for child in (node.named_children if hasattr(node, "named_children") else node.children):
            if child and getattr(child, "is_named", True):
                children.append(
                    self._ts_node_to_ast(child, source_code, file_path, depth + 1, max_depth)
                )

        # Short snippet for leaf nodes
        snippet = ""
        if node.child_count == 0 and node.end_byte - node.start_byte < 120:
            snippet = source_code[node.start_byte:node.end_byte]

        return ASTNode(
            node_id=f"{node.type}_{node.start_point[0]}_{node.start_point[1]}_{id(node) % 10000}",
            node_type=node.type,
            name=name or "",
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_col=node.start_point[1],
            end_col=node.end_point[1],
            code_snippet=snippet,
            children=children,
        )

    @staticmethod
    def _extract_node_name(node, source_code: str) -> Optional[str]:
        """Extract a meaningful name from a tree-sitter node."""
        if node.type in (
            "identifier", "property_identifier", "type_identifier",
            "field_identifier", "shorthand_property_identifier",
        ):
            return node.text.decode("utf-8") if isinstance(node.text, bytes) else str(node.text)

        name_child = node.child_by_field_name("name") if hasattr(node, "child_by_field_name") else None
        if name_child:
            text = name_child.text
            return text.decode("utf-8") if isinstance(text, bytes) else str(text)

        if "literal" in node.type or node.type in ("string", "number", "true", "false", "null", "none"):
            text = node.text.decode("utf-8") if isinstance(node.text, bytes) else str(node.text)
            return text[:40] + ("..." if len(text) > 40 else "") if text else None

        return None

    # ------------------------------------------------------------------
    # Regex fallback parsing (when tree-sitter is unavailable)
    # ------------------------------------------------------------------

    def _parse_fallback(
        self, source_code: str, language: str, file_path: Optional[str]
    ) -> Optional[ASTNode]:
        """Regex-based parsing for basic structure extraction."""
        lines = source_code.split("\n")
        fp = file_path or "unknown"

        if language in ("javascript", "typescript", "tsx"):
            children = self._fb_js(lines, fp)
        elif language == "python":
            children = self._fb_python(lines, fp)
        elif language == "java":
            children = self._fb_java(lines, fp)
        elif language in ("go",):
            children = self._fb_go(lines, fp)
        elif language in ("c", "cpp"):
            children = self._fb_c(lines, fp)
        else:
            children = []

        return ASTNode(
            node_id="root",
            node_type="source_file",
            name=fp,
            file_path=fp,
            start_line=1,
            end_line=len(lines),
            children=children,
            code_snippet=source_code[:500],
        )

    # --- JS fallback ---
    def _fb_js(self, lines, fp):
        children = []
        func_pats = [
            r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(",
            r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(",
            r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?function",
            r"^\s*(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{",
        ]
        class_pat = r"^\s*(?:export\s+)?class\s+(\w+)"
        for i, line in enumerate(lines, 1):
            m = re.match(class_pat, line)
            if m:
                children.append(ASTNode(node_id=f"class_{i}", node_type="class_declaration",
                                        name=m.group(1), file_path=fp, start_line=i, end_line=i))
                continue
            for p in func_pats:
                m = re.match(p, line)
                if m:
                    children.append(ASTNode(node_id=f"func_{i}", node_type="function_declaration",
                                            name=m.group(1), file_path=fp, start_line=i, end_line=i))
                    break
        return children

    # --- Python fallback ---
    def _fb_python(self, lines, fp):
        children = []
        for i, line in enumerate(lines, 1):
            m = re.match(r"^\s*class\s+(\w+)", line)
            if m:
                indent = len(line) - len(line.lstrip())
                end = self._fb_python_block_end(lines, i, indent)
                children.append(ASTNode(node_id=f"class_{i}", node_type="class_definition",
                                        name=m.group(1), file_path=fp, start_line=i, end_line=end))
                continue
            m = re.match(r"^\s*(?:async\s+)?def\s+(\w+)\s*\(", line)
            if m:
                indent = len(line) - len(line.lstrip())
                end = self._fb_python_block_end(lines, i, indent)
                children.append(ASTNode(node_id=f"func_{i}", node_type="function_definition",
                                        name=m.group(1), file_path=fp, start_line=i, end_line=end))
        return children

    @staticmethod
    def _fb_python_block_end(lines, start_1based: int, def_indent: int) -> int:
        """Find the last line of a Python block by tracking indentation."""
        last = start_1based
        for i in range(start_1based, len(lines)):  # 0-based index = start_1based
            line = lines[i]
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue  # blank / comment — don't break yet
            cur_indent = len(line) - len(line.lstrip())
            if cur_indent <= def_indent and stripped:
                break
            last = i + 1  # back to 1-based
        return last

    # --- Java fallback ---
    def _fb_java(self, lines, fp):
        children = []
        for i, line in enumerate(lines, 1):
            m = re.match(r"^\s*(?:public|private|protected)?\s*(?:abstract|final)?\s*class\s+(\w+)", line)
            if m:
                children.append(ASTNode(node_id=f"class_{i}", node_type="class_declaration",
                                        name=m.group(1), file_path=fp, start_line=i, end_line=i))
                continue
            m = re.match(r"^\s*(?:public|private|protected)?\s*(?:static)?\s*\w+\s+(\w+)\s*\(", line)
            if m:
                children.append(ASTNode(node_id=f"method_{i}", node_type="method_declaration",
                                        name=m.group(1), file_path=fp, start_line=i, end_line=i))
        return children

    # --- Go fallback ---
    def _fb_go(self, lines, fp):
        children = []
        for i, line in enumerate(lines, 1):
            m = re.match(r"^\s*func\s+(?:\(\s*\w+\s+\*?\w+\s*\)\s+)?(\w+)\s*\(", line)
            if m:
                children.append(ASTNode(node_id=f"func_{i}", node_type="function_declaration",
                                        name=m.group(1), file_path=fp, start_line=i, end_line=i))
            m2 = re.match(r"^\s*type\s+(\w+)\s+struct", line)
            if m2:
                children.append(ASTNode(node_id=f"struct_{i}", node_type="type_declaration",
                                        name=m2.group(1), file_path=fp, start_line=i, end_line=i))
        return children

    # --- C/C++ fallback ---
    def _fb_c(self, lines, fp):
        children = []
        for i, line in enumerate(lines, 1):
            m = re.match(r"^\s*(?:\w+\s+)+(\w+)\s*\([^)]*\)\s*\{", line)
            if m:
                children.append(ASTNode(node_id=f"func_{i}", node_type="function_definition",
                                        name=m.group(1), file_path=fp, start_line=i, end_line=i))
        return children

    # ------------------------------------------------------------------
    # AST querying helpers
    # ------------------------------------------------------------------

    def find_node_at_line(self, root: ASTNode, line_number: int) -> Optional[ASTNode]:
        """Find the most specific AST node containing the given line."""
        if not (root.start_line <= line_number <= root.end_line):
            return None
        best = root
        for child in root.children:
            result = self.find_node_at_line(child, line_number)
            if result:
                best = result
        return best

    def find_path_to_line(self, root: ASTNode, line_number: int) -> List[ASTNode]:
        """Return the path from root to the node at the given line."""
        path: List[ASTNode] = []

        def walk(n: ASTNode) -> bool:
            if n.start_line <= line_number <= n.end_line:
                path.append(n)
                for child in n.children:
                    if walk(child):
                        return True
                return True
            return False

        walk(root)
        return path

    def get_context(
        self, root: ASTNode, line_number: int, context_lines: int = 10
    ) -> ASTContext:
        """
        Get context information for a specific line in the AST.

        Returns an ASTContext matching the model schema with:
        - error_node, parent_nodes, child_nodes, sibling_nodes
        """
        node = self.find_node_at_line(root, line_number)
        path = self.find_path_to_line(root, line_number)

        parent_function = None
        parent_class = None

        for n in path:
            nt = n.node_type.lower()
            if any(kw in nt for kw in ("function", "method", "def")):
                parent_function = n
            elif "class" in nt:
                parent_class = n

        # Siblings = other children of the parent function/class
        parent = parent_function or parent_class or root
        siblings = [c for c in parent.children if c != node]

        return ASTContext(
            error_node=node,
            parent_nodes=path[:-1] if path else [],
            child_nodes=node.children if node else [],
            sibling_nodes=siblings,
        )

    # ------------------------------------------------------------------
    # Visualization
    # ------------------------------------------------------------------

    def generate_visualization(
        self, root: ASTNode, error_line: Optional[int] = None, max_depth: int = 5
    ) -> ASTVisualization:
        """Generate an interactive SVG visualization of the AST."""
        width = 800
        node_height = 35
        indent = 25

        nodes_data: List[Dict[str, Any]] = []

        def collect(node: ASTNode, depth: int = 0, y_offset: int = 0) -> int:
            if depth > max_depth:
                return y_offset
            is_error = bool(error_line and node.start_line <= error_line <= node.end_line)
            nodes_data.append({
                "name": node.name or node.node_type,
                "type": node.node_type,
                "depth": depth,
                "y": y_offset,
                "line": node.start_line,
                "is_error": is_error,
            })
            y = y_offset + node_height
            for child in node.children[:15]:
                y = collect(child, depth + 1, y)
            return y

        total_h = collect(root)

        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {total_h + 20}" '
            f'style="font-family:monospace;font-size:12px;">',
            '<style>.node:hover rect{fill:#e0e0e0}'
            '.err rect{fill:#ffcccc!important;stroke:#ff0000;stroke-width:2}</style>',
        ]
        for d in nodes_data:
            x = d["depth"] * indent + 10
            y = d["y"] + 10
            cls = "node err" if d["is_error"] else "node"
            svg_parts.append(
                f'<g class="{cls}" data-line="{d["line"]}">'
                f'<rect x="{x}" y="{y}" width="{width - x - 20}" height="{node_height - 4}" '
                f'fill="#f0f0f0" rx="3"/>'
                f'<text x="{x + 5}" y="{y + 18}" fill="#333">'
                f'{d["type"]}: {d["name"]} (L{d["line"]})</text></g>'
            )
        svg_parts.append("</svg>")

        return ASTVisualization(
            svg_content="\n".join(svg_parts),
            html_content="",
            nodes_data=nodes_data,
            tree_depth=max_depth,
            total_nodes=len(nodes_data),
        )

    # ------------------------------------------------------------------
    # Utility – convert ASTNode to JSON-friendly dict (for API responses)
    # ------------------------------------------------------------------

    @staticmethod
    def ast_to_dict(node: ASTNode, max_depth: int = 15, depth: int = 0) -> Dict[str, Any]:
        """Convert ASTNode tree to a plain dict for JSON serialisation."""
        if depth > max_depth:
            return {"type": node.node_type, "name": node.name, "truncated": True}
        return {
            "id": node.node_id,
            "type": node.node_type,
            "name": node.name,
            "loc": {
                "start": {"line": node.start_line, "column": node.start_col},
                "end": {"line": node.end_line, "column": node.end_col},
            },
            "snippet": (node.code_snippet or "")[:100],
            "children": [
                ASTService.ast_to_dict(c, max_depth, depth + 1)
                for c in node.children
            ],
        }


# ============================================================================
# Singleton
# ============================================================================

_ast_service: Optional[ASTService] = None


def get_ast_service() -> ASTService:
    """Get or create the AST service singleton."""
    global _ast_service
    if _ast_service is None:
        _ast_service = ASTService()
    return _ast_service
