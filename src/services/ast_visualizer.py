"""
AST Visualization Service - Python port of Visualizer/server.js

Provides the same visualization tree building, cross-file reference detection,
import/export extraction, and project visualization as the Node.js server,
but using Python's tree-sitter bindings.

All output formats match what the React frontend (App.jsx, TreeVisualization.jsx) expects.
"""

import os
import uuid
import zipfile
import io
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple

from utils.logger import setup_colored_logger

logger = setup_colored_logger("ast_visualizer")

# Reuse the existing ASTService & its language maps
from services.ast_service import (
    ASTService,
    EXTENSION_TO_LANGUAGE,
    LANGUAGE_DISPLAY,
)


# ════════════════════════════════════════════════════════════════
#  Common field names for tree-sitter nodes
# ════════════════════════════════════════════════════════════════

COMMON_FIELDS = [
    "name", "body", "parameters", "arguments", "value", "left", "right",
    "condition", "consequence", "alternative", "initializer", "update",
    "declarator", "type", "superclass", "interfaces", "object", "property",
    "function", "callee", "index", "key", "element", "operand", "operator",
    "source", "specifier", "alias", "module_name", "return_type", "decorator",
    "receiver", "field", "method", "class", "expression", "statement",
]

# Skip these directories when processing ZIP files
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "target", "build", "dist", "__MACOSX", ".tox", ".mypy_cache",
}


# ════════════════════════════════════════════════════════════════
#  Visualization tree builder
# ════════════════════════════════════════════════════════════════

def _node_text(node) -> str:
    """Get text from a tree-sitter node, handling bytes vs str."""
    text = node.text
    if isinstance(text, bytes):
        return text.decode("utf-8", errors="replace")
    return str(text) if text else ""


def _extract_node_name(node, source_code: str) -> Optional[str]:
    """Extract a meaningful name from a tree-sitter node (mirrors JS extractNodeName)."""
    ntype = node.type

    # Identifiers
    if ntype in ("identifier", "property_identifier", "type_identifier", "field_identifier"):
        return _node_text(node)

    # Function/class with name field
    name_child = node.child_by_field_name("name")
    if name_child:
        return _node_text(name_child)

    # Literals
    if "literal" in ntype or ntype in ("string", "number", "integer", "float"):
        txt = _node_text(node)
        if txt and len(txt) < 50:
            return txt[:30] + "..." if len(txt) > 30 else txt

    return None


def build_visualization_tree(
    node, source_code: str, depth: int = 0, max_depth: int = 15
) -> Optional[Dict[str, Any]]:
    """Build the visualization tree dict matching the Node.js format.

    Returns dict with: id, type, name, loc, children, isNamed, fieldName, text
    """
    if node is None or depth > max_depth:
        return None

    start = node.start_point
    end = node.end_point

    rand_suffix = uuid.uuid4().hex[:6]
    result: Dict[str, Any] = {
        "id": f"{node.type}_{start[0]}_{start[1]}_{rand_suffix}",
        "type": node.type,
        "name": _extract_node_name(node, source_code),
        "loc": {
            "start": {"line": start[0] + 1, "column": start[1]},
            "end": {"line": end[0] + 1, "column": end[1]},
        },
        "children": [],
        "isNamed": node.is_named,
        "fieldName": None,
    }

    # For leaf nodes, include text
    if node.child_count == 0:
        txt = _node_text(node)
        if txt and len(txt) < 100:
            result["text"] = txt

    # Process named children
    named_children = (
        node.named_children if hasattr(node, "named_children") else
        [c for c in node.children if c.is_named]
    )

    for child in named_children:
        child_tree = build_visualization_tree(child, source_code, depth + 1, max_depth)
        if child_tree:
            # Try to find field name
            for field in COMMON_FIELDS:
                fchild = node.child_by_field_name(field)
                if fchild and fchild.id == child.id:
                    child_tree["fieldName"] = field
                    break
            result["children"].append(child_tree)

    return result


# ════════════════════════════════════════════════════════════════
#  Import/Export/Declaration extraction
# ════════════════════════════════════════════════════════════════

def _find_child_by_type(node, ntype: str):
    """Find first named child with the given type."""
    if not node:
        return None
    for child in (node.named_children if hasattr(node, "named_children") else node.children):
        if child.type == ntype:
            return child
    return None


def _find_children_by_type(node, ntype: str) -> list:
    """Find all named children with the given type."""
    if not node:
        return []
    return [c for c in (node.named_children if hasattr(node, "named_children") else node.children) if c.type == ntype]


def extract_imports(root_node, source_code: str, language: str) -> List[Dict]:
    """Extract imports/requires from AST (mirrors JS extractImports)."""
    imports: List[Dict] = []
    seen: Set[str] = set()

    def add_import(imp: Dict):
        key = f"{imp['source']}:{imp['line']}"
        if key not in seen:
            seen.add(key)
            imports.append(imp)

    def walk(node):
        if not node:
            return
        ntype = node.type

        # ── JavaScript/TypeScript ──
        if ntype == "import_statement":
            source = node.child_by_field_name("source")
            if source:
                source_path = _node_text(source).strip("'\"")
                specifiers = _extract_specifiers(node)
                add_import({
                    "source": source_path,
                    "specifiers": specifiers or [{"imported": "*", "local": "*"}],
                    "line": node.start_point[0] + 1,
                    "isRelative": source_path.startswith(".") or source_path.startswith("/"),
                })

        # CommonJS require
        if ntype == "call_expression":
            callee = node.child_by_field_name("function")
            if callee and _node_text(callee) == "require":
                args = node.child_by_field_name("arguments")
                if args:
                    named = args.named_children if hasattr(args, "named_children") else [c for c in args.children if c.is_named]
                    if named:
                        arg = named[0]
                        if arg.type in ("string", "string_literal"):
                            sp = _node_text(arg).strip("'\"")
                            add_import({
                                "source": sp,
                                "specifiers": [{"imported": "*", "local": "*"}],
                                "line": node.start_point[0] + 1,
                                "isRelative": sp.startswith(".") or sp.startswith("/"),
                            })

        # ── Python ──
        if language == "Python":
            if ntype == "import_statement":
                dotted = _find_children_by_type(node, "dotted_name")
                for d in dotted:
                    module_path = _node_text(d)
                    short = module_path.split(".")[-1]
                    add_import({
                        "source": module_path,
                        "specifiers": [{"imported": short, "local": short}],
                        "line": node.start_point[0] + 1,
                        "isRelative": False,
                    })

            if ntype == "import_from_statement":
                module_path = ""
                is_relative = False
                specifiers: List[Dict] = []

                rel = _find_child_by_type(node, "relative_import")
                if rel:
                    is_relative = True
                    prefix = _find_child_by_type(rel, "import_prefix")
                    dotted = _find_child_by_type(rel, "dotted_name")
                    module_path = (_node_text(prefix) if prefix else "") + (_node_text(dotted) if dotted else "")
                else:
                    dotted_names = _find_children_by_type(node, "dotted_name")
                    if dotted_names:
                        module_path = _node_text(dotted_names[0])

                # Imported names
                dotted_names = _find_children_by_type(node, "dotted_name")
                start_idx = 0 if rel or not dotted_names else 1
                for i in range(start_idx, len(dotted_names)):
                    txt = _node_text(dotted_names[i])
                    specifiers.append({"imported": txt, "local": txt})

                aliased = _find_children_by_type(node, "aliased_import")
                for ai in aliased:
                    name = _find_child_by_type(ai, "dotted_name") or _find_child_by_type(ai, "identifier")
                    alias = _find_child_by_type(ai, "identifier")
                    if name:
                        specifiers.append({
                            "imported": _node_text(name),
                            "local": _node_text(alias) if alias else _node_text(name),
                        })

                if module_path or is_relative:
                    add_import({
                        "source": module_path or ".",
                        "specifiers": specifiers or [{"imported": "*", "local": "*"}],
                        "line": node.start_point[0] + 1,
                        "isRelative": is_relative,
                    })

        # ── Java ──
        if language == "Java" and ntype == "import_declaration":
            scoped = _find_child_by_type(node, "scoped_identifier")
            if scoped:
                full = _node_text(scoped)
                short = full.split(".")[-1]
                add_import({
                    "source": full,
                    "specifiers": [{"imported": short, "local": short}],
                    "line": node.start_point[0] + 1,
                    "isRelative": False,
                })

        # ── Go ──
        if language == "Go" and ntype in ("import_declaration", "import_spec"):
            path_node = node.child_by_field_name("path")
            if path_node:
                ip = _node_text(path_node).strip('"')
                short = ip.split("/")[-1]
                add_import({
                    "source": ip,
                    "specifiers": [{"imported": short, "local": short}],
                    "line": node.start_point[0] + 1,
                    "isRelative": ip.startswith("./"),
                })
            slit = _find_child_by_type(node, "interpreted_string_literal")
            if slit:
                ip = _node_text(slit).strip('"')
                short = ip.split("/")[-1]
                add_import({
                    "source": ip,
                    "specifiers": [{"imported": short, "local": short}],
                    "line": node.start_point[0] + 1,
                    "isRelative": ip.startswith("./"),
                })

        # ── C/C++ ──
        if language in ("C", "C++", "C Header", "C++ Header") and ntype == "preproc_include":
            path_node = node.child_by_field_name("path")
            slit = _find_child_by_type(node, "string_literal") or _find_child_by_type(node, "system_lib_string")
            actual = path_node or slit
            if actual:
                txt = _node_text(actual).strip('<>"')
                add_import({
                    "source": txt,
                    "specifiers": [{"imported": "*", "local": "*"}],
                    "line": node.start_point[0] + 1,
                    "isRelative": _node_text(actual).startswith('"'),
                })

        # ── Rust ──
        if language == "Rust" and ntype == "use_declaration":
            arg = node.child_by_field_name("argument")
            scoped = _find_child_by_type(node, "scoped_identifier") or _find_child_by_type(node, "use_wildcard") or _find_child_by_type(node, "scoped_use_list")
            pn = arg or scoped
            if pn:
                txt = _node_text(pn)
                short = txt.split("::")[-1]
                add_import({
                    "source": txt,
                    "specifiers": [{"imported": short, "local": short}],
                    "line": node.start_point[0] + 1,
                    "isRelative": txt.startswith("crate::") or txt.startswith("self::") or txt.startswith("super::"),
                })

        # ── C# ──
        if language == "C#" and ntype == "using_directive":
            nn = node.child_by_field_name("name") or _find_child_by_type(node, "qualified_name") or _find_child_by_type(node, "identifier")
            if nn:
                txt = _node_text(nn)
                short = txt.split(".")[-1]
                add_import({
                    "source": txt,
                    "specifiers": [{"imported": short, "local": short}],
                    "line": node.start_point[0] + 1,
                    "isRelative": False,
                })

        # ── Ruby ──
        if language == "Ruby" and ntype == "call":
            method = node.child_by_field_name("method")
            if method and _node_text(method) in ("require", "require_relative"):
                args = node.child_by_field_name("arguments")
                if args:
                    named = args.named_children if hasattr(args, "named_children") else [c for c in args.children if c.is_named]
                    if named:
                        rp = _node_text(named[0]).strip("'\"")
                        add_import({
                            "source": rp,
                            "specifiers": [{"imported": "*", "local": "*"}],
                            "line": node.start_point[0] + 1,
                            "isRelative": _node_text(method) == "require_relative" or rp.startswith("./"),
                        })

        # Recurse into named children
        children = node.named_children if hasattr(node, "named_children") else [c for c in node.children if c.is_named]
        for child in children:
            walk(child)

    walk(root_node)
    return imports


def _extract_specifiers(node) -> List[Dict]:
    """Extract import specifiers recursively."""
    specs: List[Dict] = []

    def _walk(n):
        if not n:
            return
        if n.type in ("identifier", "import_specifier"):
            name_node = n.child_by_field_name("name")
            alias_node = n.child_by_field_name("alias")
            name = _node_text(name_node) if name_node else _node_text(n)
            alias = _node_text(alias_node) if alias_node else None
            specs.append({"imported": name, "local": alias or name})
        children = n.named_children if hasattr(n, "named_children") else [c for c in n.children if c.is_named]
        for child in children:
            _walk(child)

    _walk(node)
    return specs


def extract_exports(root_node, source_code: str, language: str) -> List[Dict]:
    """Extract exports from AST."""
    exports: List[Dict] = []

    def walk(node):
        if not node:
            return
        ntype = node.type
        if ntype in ("export_statement", "export_declaration"):
            decl = node.child_by_field_name("declaration")
            name_node = decl.child_by_field_name("name") if decl else None
            exports.append({
                "name": _node_text(name_node) if name_node else "default",
                "type": "function" if decl and decl.type == "function_declaration" else "other",
                "line": node.start_point[0] + 1,
                "isDefault": "default" in _node_text(node),
            })
        children = node.named_children if hasattr(node, "named_children") else [c for c in node.children if c.is_named]
        for child in children:
            walk(child)

    walk(root_node)
    return exports


def extract_declarations(root_node, source_code: str, language: str) -> List[Dict]:
    """Extract top-level declarations from AST."""
    declarations: List[Dict] = []

    def walk(node, depth: int = 0):
        if not node or depth > 5:
            return
        ntype = node.type
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        # Functions
        if ntype in ("function_declaration", "function_definition", "method_definition",
                      "method_declaration", "function_item"):
            nn = node.child_by_field_name("name")
            if nn:
                declarations.append({"name": _node_text(nn), "type": "function",
                                     "line": start_line, "endLine": end_line})

        # Classes
        if ntype in ("class_declaration", "class_definition", "class_specifier", "struct_item"):
            nn = node.child_by_field_name("name")
            if nn:
                declarations.append({"name": _node_text(nn), "type": "class",
                                     "line": start_line, "endLine": end_line})

        # Variables
        if ntype in ("variable_declaration", "lexical_declaration", "const_declaration",
                      "let_declaration", "variable_declarator"):
            nn = node.child_by_field_name("name")
            if nn:
                declarations.append({"name": _node_text(nn), "type": "variable",
                                     "line": start_line, "endLine": end_line})

        # Only recurse into top-level containers
        if depth == 0 or ntype in ("program", "module", "translation_unit"):
            children = node.named_children if hasattr(node, "named_children") else [c for c in node.children if c.is_named]
            for child in children:
                walk(child, depth + 1)

    walk(root_node)
    return declarations


# ════════════════════════════════════════════════════════════════
#  Error path detection
# ════════════════════════════════════════════════════════════════

def find_path_to_line(node, target_line: int, path: list = None) -> Optional[list]:
    """Find path of nodes from root to the node at target_line."""
    if path is None:
        path = []
    if not node:
        return None

    start_line = node.start_point[0] + 1
    end_line = node.end_point[0] + 1

    if target_line < start_line or target_line > end_line:
        return None

    name_child = node.child_by_field_name("name")
    current = {
        "type": node.type,
        "line": start_line,
        "name": _node_text(name_child) if name_child else None,
    }
    current_path = path + [current]

    children = node.named_children if hasattr(node, "named_children") else [c for c in node.children if c.is_named]
    for child in children:
        found = find_path_to_line(child, target_line, current_path)
        if found:
            return found

    return current_path


def mark_error_path(tree: Dict, error_path: list):
    """Mark nodes on the error path in the visualization tree."""
    if not tree or not error_path:
        return
    error_lines = {p["line"] for p in error_path}

    def mark(node: Dict):
        if not node:
            return
        if node.get("loc", {}).get("start", {}).get("line") in error_lines:
            node["isError"] = True
        for child in node.get("children", []):
            mark(child)

    mark(tree)


# ════════════════════════════════════════════════════════════════
#  Cross-file reference resolution
# ════════════════════════════════════════════════════════════════

def resolve_import_path(
    current_file: str, import_path: str, available_files: List[str], language: str
) -> Optional[str]:
    """Resolve an import path to an actual file in the project."""
    current_dir = os.path.dirname(current_file).replace("\\", "/")

    # ── Python ──
    if language == "Python":
        resolved = None
        if import_path.startswith("."):
            dot_count = len(import_path) - len(import_path.lstrip("."))
            target_dir = current_dir
            for _ in range(1, dot_count):
                target_dir = os.path.dirname(target_dir).replace("\\", "/")
            module_name = import_path[dot_count:].replace(".", "/")
            resolved = f"{target_dir}/{module_name}" if (target_dir and module_name) else (target_dir or module_name)
        else:
            resolved = import_path.replace(".", "/")

        if resolved:
            resolved = resolved.lstrip("./")
            if resolved in available_files:
                return resolved
            if f"{resolved}.py" in available_files:
                return f"{resolved}.py"
            if f"{resolved}/__init__.py" in available_files:
                return f"{resolved}/__init__.py"
            mod = resolved.split("/")[-1]
            for f in available_files:
                if f.endswith(f"/{mod}.py") or f == f"{mod}.py":
                    return f
        return None

    # Non-relative → skip
    if not import_path.startswith(".") and not import_path.startswith("/"):
        return None

    import posixpath
    resolved = posixpath.join(current_dir, import_path).replace("\\", "/")
    resolved = resolved.lstrip("./")

    if resolved in available_files:
        return resolved

    supported_exts = list(EXTENSION_TO_LANGUAGE.keys())
    for ext in supported_exts:
        if f"{resolved}{ext}" in available_files:
            return f"{resolved}{ext}"
    for ext in supported_exts:
        idx = f"{resolved}/index{ext}"
        if idx in available_files:
            return idx

    return None


def mark_reference_node(tree: Dict, line: int, ref_info: Dict) -> bool:
    """Mark a tree node at a specific line as a cross-file reference."""
    if not tree:
        return False
    if tree.get("loc", {}).get("start", {}).get("line") == line:
        tree.update(ref_info)
        return True
    for child in tree.get("children", []):
        if mark_reference_node(child, line, ref_info):
            return True
    return False


# ════════════════════════════════════════════════════════════════
#  Project visualization builder
# ════════════════════════════════════════════════════════════════

class ASTVisualizer:
    """Orchestrates AST parsing, visualization tree building, and cross-file references."""

    def __init__(self):
        self._ast_service = ASTService()

    # ------------------------------------------------------------------
    # Single file parsing
    # ------------------------------------------------------------------

    def parse_single_file(self, filename: str, content: str) -> Dict[str, Any]:
        """Parse a single file and return visualization data."""
        language = self._ast_service.detect_language(filename)
        if not language:
            return {
                "filename": filename,
                "content": content,
                "tree": None,
                "declarations": [],
                "language": "Unknown",
                "error": f"Unsupported file type: {Path(filename).suffix}",
            }

        try:
            root = self._ast_service.parse_code(content, language, filename)
            if not root:
                raise RuntimeError("Parser returned None")

            # We need the raw tree-sitter node for visualization
            parser, _ = self._ast_service._get_parser(language)
            if parser is None:
                raise RuntimeError("No parser available")

            tree = parser.parse(content.encode("utf-8"))
            ts_root = tree.root_node

            viz_tree = build_visualization_tree(ts_root, content)
            display_lang = LANGUAGE_DISPLAY.get(language, language)
            declarations = extract_declarations(ts_root, content, display_lang)

            return {
                "filename": filename,
                "content": content,
                "tree": viz_tree,
                "declarations": declarations,
                "language": display_lang,
                "error": None,
            }
        except Exception as e:
            logger.warning(f"Failed to parse {filename}: {e}")
            return {
                "filename": filename,
                "content": content,
                "tree": None,
                "declarations": [],
                "language": LANGUAGE_DISPLAY.get(language, language) if language else "Unknown",
                "error": str(e),
            }

    # ------------------------------------------------------------------
    # Code snippet parsing
    # ------------------------------------------------------------------

    def parse_code_snippet(
        self, code: str, filename: str = "code.js", error_line: Optional[int] = None
    ) -> Dict[str, Any]:
        """Parse a code snippet, optionally marking an error line."""
        language = self._ast_service.detect_language(filename)
        if not language:
            # Guess common languages
            ext = Path(filename).suffix.lower()
            language = EXTENSION_TO_LANGUAGE.get(ext)
            if not language:
                return {"error": f"Unsupported file type: {ext}", "filename": filename}

        try:
            parser, _ = self._ast_service._get_parser(language)
            if parser is None:
                raise RuntimeError(f"No parser for language: {language}")

            tree = parser.parse(code.encode("utf-8"))
            ts_root = tree.root_node
            display_lang = LANGUAGE_DISPLAY.get(language, language)

            viz_tree = build_visualization_tree(ts_root, code)
            declarations = extract_declarations(ts_root, code, display_lang)

            error_path = None
            if error_line and error_line > 0:
                error_path = find_path_to_line(ts_root, error_line)
                if error_path and viz_tree:
                    mark_error_path(viz_tree, error_path)

            return {
                "filename": filename,
                "content": code,
                "tree": viz_tree,
                "errorLine": error_line,
                "errorPath": error_path,
                "language": display_lang,
                "declarations": declarations,
            }
        except Exception as e:
            return {"error": str(e), "filename": filename}

    # ------------------------------------------------------------------
    # ZIP project parsing with cross-file references
    # ------------------------------------------------------------------

    def parse_zip_project(self, zip_buffer: bytes, original_name: str = "project") -> Dict[str, Any]:
        """Parse all files in a ZIP archive and build cross-file references."""
        files: List[Dict[str, str]] = []

        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_buffer))
        except zipfile.BadZipFile as e:
            return {"error": f"Invalid ZIP file: {e}"}

        # Find common root folder
        entries = [n for n in zf.namelist() if not n.endswith("/")]
        root_folder = ""
        if entries:
            parts = entries[0].replace("\\", "/").split("/")
            if len(parts) > 1:
                root_folder = parts[0] + "/"

        for entry in entries:
            name = entry.replace("\\", "/")
            if root_folder and name.startswith(root_folder):
                name = name[len(root_folder):]

            # Skip unwanted dirs/files
            if any(sd + "/" in name or name.startswith(sd + "/") for sd in SKIP_DIRS):
                continue
            if ".DS_Store" in name:
                continue

            ext = Path(name).suffix.lower()
            if ext not in EXTENSION_TO_LANGUAGE:
                continue

            try:
                content = zf.read(entry).decode("utf-8", errors="replace")
                files.append({"name": name, "content": content})
            except Exception:
                continue

        if not files:
            return {
                "error": "No supported source files found in ZIP",
                "supportedExtensions": list(EXTENSION_TO_LANGUAGE.keys()),
            }

        return self._build_project_visualization(files, original_name)

    # ------------------------------------------------------------------
    # Git repo project parsing
    # ------------------------------------------------------------------

    def parse_repo_directory(self, repo_path: str, project_name: str = "repo") -> Dict[str, Any]:
        """Parse all files in a local repository directory."""
        repo = Path(repo_path)
        if not repo.exists():
            return {"error": f"Repository path not found: {repo_path}"}

        files: List[Dict[str, str]] = []
        for filepath in repo.rglob("*"):
            if filepath.is_dir():
                continue
            if any(sd in filepath.parts for sd in SKIP_DIRS):
                continue
            ext = filepath.suffix.lower()
            if ext not in EXTENSION_TO_LANGUAGE:
                continue
            try:
                rel = str(filepath.relative_to(repo)).replace("\\", "/")
                content = filepath.read_text(encoding="utf-8", errors="replace")
                files.append({"name": rel, "content": content})
            except Exception:
                continue

        if not files:
            return {
                "error": "No supported source files found",
                "supportedExtensions": list(EXTENSION_TO_LANGUAGE.keys()),
            }

        return self._build_project_visualization(files, project_name)

    # ------------------------------------------------------------------
    # Internal project visualization builder
    # ------------------------------------------------------------------

    def _build_project_visualization(
        self, files: List[Dict[str, str]], project_name: str
    ) -> Dict[str, Any]:
        """Build complete project visualization with cross-file references."""
        file_names = [f["name"] for f in files]
        file_data: Dict[str, Dict] = {}
        cross_references: List[Dict] = []

        # First pass — parse all files
        for finfo in files:
            name = finfo["name"]
            content = finfo["content"]
            language = self._ast_service.detect_language(name)

            if not language:
                file_data[name] = {
                    "name": name, "content": content, "tree": None,
                    "imports": [], "exports": [], "declarations": [],
                    "language": "Unknown", "error": "Unsupported",
                }
                continue

            try:
                parser, _ = self._ast_service._get_parser(language)
                if parser is None:
                    raise RuntimeError("No parser")

                ts_tree = parser.parse(content.encode("utf-8"))
                ts_root = ts_tree.root_node
                display_lang = LANGUAGE_DISPLAY.get(language, language)

                viz_tree = build_visualization_tree(ts_root, content)
                imports = extract_imports(ts_root, content, display_lang)
                exports = extract_exports(ts_root, content, display_lang)
                declarations = extract_declarations(ts_root, content, display_lang)

                file_data[name] = {
                    "name": name, "content": content, "tree": viz_tree,
                    "imports": imports, "exports": exports,
                    "declarations": declarations, "language": display_lang,
                    "error": None,
                }
            except Exception as e:
                file_data[name] = {
                    "name": name, "content": content, "tree": None,
                    "imports": [], "exports": [], "declarations": [],
                    "language": LANGUAGE_DISPLAY.get(language, language) if language else "Unknown",
                    "error": str(e),
                }

        # Second pass — cross-file references
        for fname, data in file_data.items():
            for imp in data.get("imports", []):
                if not imp.get("isRelative"):
                    continue
                target = resolve_import_path(fname, imp["source"], file_names, data["language"])
                if not target:
                    continue
                target_data = file_data.get(target)
                if not target_data:
                    continue

                for spec in imp.get("specifiers", []):
                    imported_name = spec.get("imported", "default")
                    target_line = 1
                    te = next((e for e in target_data.get("exports", []) if e["name"] == imported_name or (imported_name == "*" and e.get("isDefault"))), None)
                    if te:
                        target_line = te["line"]
                    else:
                        td = next((d for d in target_data.get("declarations", []) if d["name"] == imported_name), None)
                        if td:
                            target_line = td["line"]

                    ref_id = f"ref_{fname}_{imp['line']}_{target}_{uuid.uuid4().hex[:4]}"
                    cross_references.append({
                        "id": ref_id,
                        "fromFile": fname,
                        "fromLine": imp["line"],
                        "fromName": spec.get("local", imported_name),
                        "toFile": target,
                        "toLine": target_line,
                        "toName": imported_name,
                        "type": "import",
                    })

        # Mark reference nodes in trees
        for ref in cross_references:
            from_data = file_data.get(ref["fromFile"])
            if from_data and from_data.get("tree"):
                mark_reference_node(from_data["tree"], ref["fromLine"], {
                    "isReference": True,
                    "referenceId": ref["id"],
                    "direction": "outgoing",
                    "targetFile": ref["toFile"],
                    "targetLine": ref["toLine"],
                    "targetName": ref["toName"],
                })

        # Build result
        result_files = {}
        for fname, data in file_data.items():
            result_files[fname] = {
                "name": data["name"],
                "content": data["content"],
                "tree": data["tree"],
                "declarations": data["declarations"],
                "imports": data["imports"],
                "exports": data["exports"],
                "language": data["language"],
                "error": data["error"],
                "incomingRefs": [r for r in cross_references if r["toFile"] == fname],
                "outgoingRefs": [r for r in cross_references if r["fromFile"] == fname],
            }

        languages = list({d["language"] for d in file_data.values() if d["language"] != "Unknown"})

        return {
            "files": result_files,
            "references": cross_references,
            "summary": {
                "totalFiles": len(files),
                "totalReferences": len(cross_references),
                "languages": sorted(languages),
            },
            "projectName": project_name,
            "supportedExtensions": list(EXTENSION_TO_LANGUAGE.keys()),
        }


# ════════════════════════════════════════════════════════════════
#  Languages endpoint helper
# ════════════════════════════════════════════════════════════════

def get_languages_info() -> Dict[str, Any]:
    """Get supported languages info matching the Node.js /languages endpoint format."""
    languages: Dict[str, List[str]] = {}
    for ext, lang_key in EXTENSION_TO_LANGUAGE.items():
        display_name = LANGUAGE_DISPLAY.get(lang_key, lang_key)
        if display_name not in languages:
            languages[display_name] = []
        languages[display_name].append(ext)
    return {
        "languages": languages,
        "extensions": list(EXTENSION_TO_LANGUAGE.keys()),
    }


# ════════════════════════════════════════════════════════════════
#  Singleton
# ════════════════════════════════════════════════════════════════

_visualizer: Optional[ASTVisualizer] = None


def get_ast_visualizer() -> ASTVisualizer:
    global _visualizer
    if _visualizer is None:
        _visualizer = ASTVisualizer()
    return _visualizer
