"""
AST Trace Service for the Self-Healing Software System v2.0

Provides AST-based error tracing with cross-file reference resolution.
This service enhances error context by:
- Building complete AST for error files
- Tracing imports to find cross-file dependencies  
- Detecting project requirements (package.json, requirements.txt, etc.)
- Generating rich context for AI analysis
"""

import os
import json
import re
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Set
from dataclasses import dataclass, field

from utils.models import ASTNode, ASTContext
from utils.logger import setup_colored_logger
from services.ast_service import get_ast_service, ASTService

logger = setup_colored_logger("ast_trace_service")


# ==========================================
# Data Models for Tracing
# ==========================================

@dataclass
class Reference:
    """Cross-file reference (import/export)."""
    from_file: str
    to_file: str
    symbol_name: str
    line_number: int
    ref_type: str = "import"  # "import", "export", "call"
    resolved_path: Optional[str] = None


@dataclass
class ProjectRequirements:
    """Detected project dependencies."""
    language: str
    manifest_file: str
    manifest_content: str = ""
    dependencies: Dict[str, str] = field(default_factory=dict)  # name -> version
    dev_dependencies: Dict[str, str] = field(default_factory=dict)


@dataclass
class ASTTraceContext:
    """Complete AST trace for error analysis."""
    error_file: str
    error_line: int
    main_ast: Optional[ASTNode] = None
    references: List[Reference] = field(default_factory=list)
    referenced_files: Dict[str, ASTNode] = field(default_factory=dict)  # file -> AST
    error_path: List[ASTNode] = field(default_factory=list)  # Path from root to error
    source_code: str = ""
    error_context_code: str = ""  # Code around error line
    requirements: Optional[ProjectRequirements] = None
    # Rich context built from AST tracing (stored for report display)
    ai_context: str = ""
    # Call chain extracted from stack trace: [(file, line, func), ...]
    call_chain: List[Tuple[str, int, str]] = field(default_factory=list)
    # Full function bodies collected for AI
    traced_functions: Dict[str, str] = field(default_factory=dict)  # "file:func" -> body


class ASTTraceService:
    """
    Service for building rich AST-based error context.
    
    Features:
    - Complete AST trace with error line annotation
    - Cross-file reference resolution (imports/exports)
    - Project requirements detection
    - Rich context building for AI consumption
    """
    
    # Common requirement manifest files
    MANIFEST_FILES = {
        "javascript": ["package.json"],
        "typescript": ["package.json"],
        "python": ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"],
        "java": ["pom.xml", "build.gradle", "build.gradle.kts"],
        "go": ["go.mod"],
        "rust": ["Cargo.toml"],
        "ruby": ["Gemfile"],
        "php": ["composer.json"],
    }
    
    def __init__(self):
        """Initialize the AST trace service."""
        self.ast_service = get_ast_service()
    
    def trace_error(
        self,
        error_file: str,
        error_line: int,
        repo_path: str,
        source_code: Optional[str] = None,
    ) -> ASTTraceContext:
        """
        Build complete AST trace for an error.
        
        Args:
            error_file: Path to the file containing the error
            error_line: Line number of the error
            repo_path: Root path of the repository
            source_code: Optional source code (if file content is provided)
            
        Returns:
            ASTTraceContext with full trace information
        """
        logger.info(f"Tracing error at {error_file}:{error_line}")
        
        # Initialize context
        context = ASTTraceContext(
            error_file=error_file,
            error_line=error_line
        )
        
        # Get source code
        full_path = os.path.join(repo_path, error_file) if repo_path else error_file
        if source_code:
            context.source_code = source_code
        elif os.path.exists(full_path):
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    context.source_code = f.read()
            except Exception as e:
                logger.error(f"Failed to read file {full_path}: {e}")
        
        # Extract context around error line
        if context.source_code:
            context.error_context_code = self._extract_context_lines(
                context.source_code, error_line, context_lines=10
            )
        
        # Parse main file AST
        if context.source_code:
            language = self.ast_service.detect_language(error_file)
            if language:
                context.main_ast = self.ast_service.parse_code(
                    context.source_code, language, error_file
                )
                
                # Find path to error line
                if context.main_ast:
                    context.error_path = self._find_error_path(
                        context.main_ast, error_line
                    )
        
        # Extract references and trace to other files
        if context.source_code:
            context.references = self._extract_references(
                context.source_code, error_file
            )
            
            # Resolve references to actual files
            context.references = self._resolve_references(
                context.references, repo_path
            )
        
        if context.source_code:
            # Parse referenced files (limited depth)
            for ref in context.references[:5]:  # Limit to 5 references
                if ref.resolved_path and ref.resolved_path not in context.referenced_files:
                    referenced_ast = self.ast_service.parse_file(ref.resolved_path)
                    if referenced_ast:
                        context.referenced_files[ref.resolved_path] = referenced_ast
        
        # Detect project requirements
        if repo_path:
            context.requirements = self.detect_requirements(repo_path)
        
        logger.info(f"Trace complete: {len(context.references)} refs, "
                   f"{len(context.referenced_files)} resolved files")
        
        return context
    
    def _extract_context_lines(
        self, source_code: str, error_line: int, context_lines: int = 10
    ) -> str:
        """Extract code lines around the error."""
        lines = source_code.split('\n')
        start = max(0, error_line - context_lines - 1)
        end = min(len(lines), error_line + context_lines)
        
        result = []
        for i, line in enumerate(lines[start:end], start + 1):
            marker = ">>> " if i == error_line else "    "
            result.append(f"{marker}{i:4d} | {line}")
        
        return '\n'.join(result)

    def _find_error_path(self, root: ASTNode, error_line: int) -> List[ASTNode]:
        """Find the path from root to the error line."""
        path = []
        
        def traverse(node: ASTNode) -> bool:
            if node.start_line <= error_line <= node.end_line:
                path.append(node)
                for child in node.children:
                    if traverse(child):
                        return True
                return True
            return False
        
        traverse(root)
        return path
    
    def _extract_references(
        self, source_code: str, file_path: str
    ) -> List[Reference]:
        """Extract import/export references from source code."""
        references = []
        lines = source_code.split('\n')
        
        # Detect language
        language = self.ast_service.detect_language(file_path)
        
        for i, line in enumerate(lines, 1):
            if language in ["javascript", "typescript"]:
                refs = self._extract_js_imports(line, i, file_path)
            elif language == "python":
                refs = self._extract_python_imports(line, i, file_path)
            elif language == "java":
                refs = self._extract_java_imports(line, i, file_path)
            elif language == "go":
                refs = self._extract_go_imports(line, i, file_path)
            else:
                refs = []
            
            references.extend(refs)
        
        return references
    
    def _extract_js_imports(
        self, line: str, line_num: int, from_file: str
    ) -> List[Reference]:
        """Extract JavaScript/TypeScript import references."""
        refs = []
        
        # ES6 imports: import X from 'path'
        es6_match = re.search(
            r"import\s+(?:{[^}]+}|[\w,\s*]+)\s+from\s+['\"]([^'\"]+)['\"]",
            line
        )
        if es6_match:
            import_path = es6_match.group(1)
            if import_path.startswith('.'):  # Relative import
                refs.append(Reference(
                    from_file=from_file,
                    to_file=import_path,
                    symbol_name=self._extract_import_symbols(line),
                    line_number=line_num,
                    ref_type="import"
                ))
        
        # CommonJS: require('path')
        cjs_match = re.search(r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", line)
        if cjs_match:
            import_path = cjs_match.group(1)
            if import_path.startswith('.'):
                refs.append(Reference(
                    from_file=from_file,
                    to_file=import_path,
                    symbol_name="",
                    line_number=line_num,
                    ref_type="require"
                ))
        
        return refs
    
    def _extract_python_imports(
        self, line: str, line_num: int, from_file: str
    ) -> List[Reference]:
        """Extract Python import references."""
        refs = []
        
        # from X import Y
        from_match = re.search(r"from\s+([\w.]+)\s+import", line)
        if from_match:
            module = from_match.group(1)
            if not module.startswith('__'):
                refs.append(Reference(
                    from_file=from_file,
                    to_file=module.replace('.', '/'),
                    symbol_name=self._extract_python_import_symbols(line),
                    line_number=line_num,
                    ref_type="import"
                ))
        
        # import X
        import_match = re.search(r"^import\s+([\w.]+)", line)
        if import_match:
            module = import_match.group(1)
            refs.append(Reference(
                from_file=from_file,
                to_file=module.replace('.', '/'),
                symbol_name=module,
                line_number=line_num,
                ref_type="import"
            ))
        
        return refs
    
    def _extract_java_imports(
        self, line: str, line_num: int, from_file: str
    ) -> List[Reference]:
        """Extract Java import references."""
        refs = []
        
        import_match = re.search(r"import\s+([\w.]+);", line)
        if import_match:
            package = import_match.group(1)
            refs.append(Reference(
                from_file=from_file,
                to_file=package.replace('.', '/'),
                symbol_name=package.split('.')[-1],
                line_number=line_num,
                ref_type="import"
            ))
        
        return refs
    
    def _extract_go_imports(
        self, line: str, line_num: int, from_file: str
    ) -> List[Reference]:
        """Extract Go import references."""
        refs = []
        
        import_match = re.search(r'"([^"]+)"', line)
        if import_match:
            import_path = import_match.group(1)
            refs.append(Reference(
                from_file=from_file,
                to_file=import_path,
                symbol_name="",
                line_number=line_num,
                ref_type="import"
            ))
        
        return refs
    
    def _extract_import_symbols(self, line: str) -> str:
        """Extract imported symbol names from JS import statement."""
        # Match { X, Y, Z }
        braces_match = re.search(r'{([^}]+)}', line)
        if braces_match:
            symbols = braces_match.group(1)
            return symbols.strip()
        
        # Match default import
        default_match = re.search(r'import\s+(\w+)\s+from', line)
        if default_match:
            return default_match.group(1)
        
        return ""
    
    def _extract_python_import_symbols(self, line: str) -> str:
        """Extract imported symbol names from Python import statement."""
        match = re.search(r'import\s+(.+)$', line)
        if match:
            return match.group(1).strip()
        return ""
    
    def _resolve_references(
        self, references: List[Reference], repo_path: str
    ) -> List[Reference]:
        """Resolve reference paths to actual file paths."""
        if not repo_path:
            return references
        
        resolved = []
        for ref in references:
            possible_paths = self._get_possible_paths(ref.to_file, repo_path)
            
            for path in possible_paths:
                if os.path.exists(path):
                    ref.resolved_path = path
                    break
            
            resolved.append(ref)
        
        return resolved
    
    def _get_possible_paths(self, import_path: str, repo_path: str) -> List[str]:
        """Generate possible file paths for an import."""
        # Clean the import path
        clean_path = import_path.lstrip('./')
        
        # Common extensions to try
        extensions = ['.js', '.jsx', '.ts', '.tsx', '.py', '.java', '.go']
        
        paths = []
        
        # Direct file
        base = os.path.join(repo_path, clean_path)
        paths.append(base)
        
        # With extensions
        for ext in extensions:
            paths.append(base + ext)
            paths.append(os.path.join(base, f"index{ext}"))
        
        return paths
    
    def detect_requirements(self, repo_path: str) -> Optional[ProjectRequirements]:
        """
        Detect project requirements from manifest files.
        
        Scans for package.json, requirements.txt, pom.xml, etc.
        """
        logger.info(f"Detecting requirements in {repo_path}")
        
        for language, manifests in self.MANIFEST_FILES.items():
            for manifest in manifests:
                manifest_path = os.path.join(repo_path, manifest)
                if os.path.exists(manifest_path):
                    try:
                        with open(manifest_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        requirements = ProjectRequirements(
                            language=language,
                            manifest_file=manifest,
                            manifest_content=content
                        )
                        
                        # Parse based on manifest type
                        if manifest == "package.json":
                            requirements = self._parse_package_json(requirements, content)
                        elif manifest == "requirements.txt":
                            requirements = self._parse_requirements_txt(requirements, content)
                        elif manifest == "pyproject.toml":
                            requirements = self._parse_pyproject_toml(requirements, content)
                        elif manifest == "pom.xml":
                            requirements = self._parse_pom_xml(requirements, content)
                        elif manifest == "go.mod":
                            requirements = self._parse_go_mod(requirements, content)
                        elif manifest == "Cargo.toml":
                            requirements = self._parse_cargo_toml(requirements, content)
                        
                        logger.info(f"Found {len(requirements.dependencies)} dependencies in {manifest}")
                        return requirements
                        
                    except Exception as e:
                        logger.error(f"Failed to parse {manifest_path}: {e}")
        
        return None
    
    def _parse_package_json(
        self, reqs: ProjectRequirements, content: str
    ) -> ProjectRequirements:
        """Parse package.json for dependencies."""
        try:
            data = json.loads(content)
            reqs.dependencies = data.get("dependencies", {})
            reqs.dev_dependencies = data.get("devDependencies", {})
        except json.JSONDecodeError:
            pass
        return reqs
    
    def _parse_requirements_txt(
        self, reqs: ProjectRequirements, content: str
    ) -> ProjectRequirements:
        """Parse requirements.txt for dependencies."""
        for line in content.split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                # Parse package==version or package>=version
                match = re.match(r'^([a-zA-Z0-9_-]+)([<>=!]+)?([\d.]+)?', line)
                if match:
                    package = match.group(1)
                    version = match.group(3) or "any"
                    reqs.dependencies[package] = version
        return reqs
    
    def _parse_pyproject_toml(
        self, reqs: ProjectRequirements, content: str
    ) -> ProjectRequirements:
        """Parse pyproject.toml for dependencies."""
        # Simple regex-based parsing for dependencies section
        deps_match = re.search(r'\[project\].*?dependencies\s*=\s*\[(.*?)\]', 
                               content, re.DOTALL)
        if deps_match:
            deps_str = deps_match.group(1)
            for dep in re.findall(r'"([^"]+)"', deps_str):
                match = re.match(r'^([a-zA-Z0-9_-]+)', dep)
                if match:
                    reqs.dependencies[match.group(1)] = "any"
        return reqs
    
    def _parse_pom_xml(
        self, reqs: ProjectRequirements, content: str
    ) -> ProjectRequirements:
        """Parse pom.xml for dependencies."""
        # Simple regex parsing for dependencies
        dep_pattern = r'<dependency>.*?<groupId>(.*?)</groupId>.*?<artifactId>(.*?)</artifactId>.*?<version>(.*?)</version>.*?</dependency>'
        for match in re.finditer(dep_pattern, content, re.DOTALL):
            group_id = match.group(1)
            artifact_id = match.group(2)
            version = match.group(3)
            reqs.dependencies[f"{group_id}:{artifact_id}"] = version
        return reqs
    
    def _parse_go_mod(
        self, reqs: ProjectRequirements, content: str
    ) -> ProjectRequirements:
        """Parse go.mod for dependencies."""
        for line in content.split('\n'):
            line = line.strip()
            if line and not line.startswith('//') and not line.startswith('module'):
                parts = line.split()
                if len(parts) >= 2:
                    reqs.dependencies[parts[0]] = parts[1]
        return reqs
    
    def _parse_cargo_toml(
        self, reqs: ProjectRequirements, content: str
    ) -> ProjectRequirements:
        """Parse Cargo.toml for dependencies."""
        in_deps = False
        for line in content.split('\n'):
            line = line.strip()
            if line == '[dependencies]':
                in_deps = True
                continue
            if line.startswith('['):
                in_deps = False
            if in_deps and '=' in line:
                parts = line.split('=', 1)
                package = parts[0].strip()
                version = parts[1].strip().strip('"\'')
                reqs.dependencies[package] = version
        return reqs
    
    def build_ai_context(self, trace: ASTTraceContext, repo_path: str = "") -> str:
        """
        Build a rich context string for AI analysis using AST tracing.

        Strategy (bottom-up from error):
        1. Parse the stack-trace / call chain to identify multi-file frames.
        2. For the bottom 3 frames (closest to error): include **full function bodies**.
        3. For frames above that: include only the call-site lines + surrounding context.
        4. Prepend import lines of every involved file.
        5. Store the result on ``trace.ai_context`` so the report can display it.
        """
        sections: list[str] = []

        # ── 1. Error location headline ──
        sections.append(f"## Error Location\n")
        sections.append(f"File: `{trace.error_file}` | Line: {trace.error_line}\n")

        # ── 2. Parse call chain from stack trace (if available) ──
        call_chain = trace.call_chain  # filled by main.py _build_call_chain

        # ── 3. Collect full function bodies for the bottom N frames ──
        FULL_BODY_DEPTH = 3
        traced_functions: dict[str, str] = {}  # "file:func_name" -> body text

        if call_chain:
            sections.append("\n## Call Chain (from stack trace, innermost first)\n")
            for idx, (cc_file, cc_line, cc_func) in enumerate(call_chain):
                tag = "→ " if idx == 0 else "  "
                sections.append(f"{tag}`{cc_file}:{cc_line}` in `{cc_func or '?'}`\n")

            # Resolve function bodies for each frame
            for idx, (cc_file, cc_line, cc_func) in enumerate(call_chain):
                body = self._extract_function_body_at_line(
                    cc_file, cc_line, trace, repo_path=repo_path
                )
                if body is None:
                    continue
                func_key = f"{cc_file}:{cc_func or f'L{cc_line}'}"
                traced_functions[func_key] = body

                if idx < FULL_BODY_DEPTH:
                    sections.append(f"\n### [{idx+1}] Full function — `{func_key}`\n")
                    sections.append(f"```\n{body}\n```\n")
                else:
                    # Just the call-site context (±3 lines)
                    snippet = self._extract_context_lines_from_body(
                        body, cc_line, context_lines=3
                    )
                    if snippet:
                        sections.append(f"\n### [{idx+1}] Call-site — `{func_key}`\n")
                        sections.append(f"```\n{snippet}\n```\n")
        else:
            # No call chain — fall back to error_path from AST
            body = self._extract_function_body_at_line(
                trace.error_file, trace.error_line, trace, repo_path=repo_path
            )
            if body:
                func_label = trace.error_file
                if trace.error_path:
                    for node in reversed(trace.error_path):
                        if "function" in node.node_type or "def" in node.node_type:
                            func_label = f"{trace.error_file}:{node.name}"
                            break
                traced_functions[func_label] = body
                sections.append(f"\n### Error function — `{func_label}`\n")
                sections.append(f"```\n{body}\n```\n")
            elif trace.error_context_code:
                sections.append(f"\n### Code Context (±10 lines around error)\n")
                sections.append(f"```\n{trace.error_context_code}\n```\n")

        # ── 4. Import lines for involved files ──
        involved_files: set[str] = set()
        if call_chain:
            involved_files = {cc[0] for cc in call_chain}
        if trace.error_file:
            involved_files.add(trace.error_file)

        import_sections: list[str] = []
        for ifile in sorted(involved_files):
            imports = self._extract_import_lines(ifile, trace)
            if imports:
                import_sections.append(f"`{ifile}` imports:\n```\n{imports}\n```\n")
        if import_sections:
            sections.append("\n## Import Context\n")
            sections.extend(import_sections)

        # ── 5. AST path to error ──
        if trace.error_path:
            sections.append(f"\n## AST Path to Error\n")
            for i, node in enumerate(trace.error_path):
                indent = "  " * i
                sections.append(f"{indent}└─ {node.node_type}: `{node.name}` "
                              f"(L{node.start_line}-{node.end_line})\n")

        # ── 6. Cross-file references ──
        if trace.references:
            sections.append(f"\n## Cross-File References\n")
            for ref in trace.references[:10]:
                resolved = "✓" if ref.resolved_path else "✗"
                sections.append(f"- [{resolved}] L{ref.line_number}: "
                              f"{ref.ref_type} `{ref.symbol_name}` from `{ref.to_file}`\n")

        # ── 7. Dependencies ──
        if trace.requirements:
            sections.append(f"\n## Dependencies ({trace.requirements.language})\n")
            for pkg, ver in list(trace.requirements.dependencies.items())[:15]:
                sections.append(f"- {pkg}: {ver}\n")

        context_str = ''.join(sections)
        trace.ai_context = context_str
        trace.traced_functions = traced_functions
        return context_str

    # ------------------------------------------------------------------
    # Helpers for rich context building
    # ------------------------------------------------------------------

    def _extract_function_body_at_line(
        self, rel_file: str, line_no: int, trace: ASTTraceContext,
        repo_path: str = "",
    ) -> Optional[str]:
        """Extract the full body of the function surrounding *line_no* in *rel_file*.

        Uses the AST tree if available (accurate line ranges), otherwise
        does an indentation-based extraction from source text.
        """
        # Determine which AST / source to use
        source = None
        ast_root = None

        # If it's the error file, use what we already have
        if rel_file == trace.error_file:
            source = trace.source_code
            ast_root = trace.main_ast
        else:
            # Check referenced files
            for ref_path, ref_ast in trace.referenced_files.items():
                # rel_file could be "utils/validator.py" while ref_path is absolute
                if ref_path.replace("\\", "/").endswith(rel_file.replace("\\", "/")):
                    ast_root = ref_ast
                    try:
                        with open(ref_path, "r", encoding="utf-8") as fh:
                            source = fh.read()
                    except Exception:
                        pass
                    break

            # Fallback: read directly from repo if not in referenced_files
            if source is None and repo_path:
                disk_path = os.path.join(repo_path, rel_file)
                if os.path.isfile(disk_path):
                    try:
                        with open(disk_path, "r", encoding="utf-8") as fh:
                            source = fh.read()
                        # Also parse the AST for this file so we get accurate end lines
                        lang = self.ast_service.detect_language(rel_file)
                        if lang:
                            ast_root = self.ast_service.parse_code(source, lang, rel_file)
                            # Cache in referenced_files for future use
                            if ast_root:
                                trace.referenced_files[disk_path] = ast_root
                    except Exception:
                        pass

        if not source:
            return None

        lines = source.split("\n")

        # Try AST-based extraction first
        if ast_root:
            enclosing = self._find_enclosing_function(ast_root, line_no)
            if enclosing and enclosing.start_line > 0 and enclosing.end_line > 0:
                start = enclosing.start_line - 1
                end = min(enclosing.end_line, len(lines))
                body_lines = []
                for idx in range(start, end):
                    ln = idx + 1
                    marker = ">>> " if ln == line_no else "    "
                    body_lines.append(f"{marker}{ln:4d} | {lines[idx]}")
                return "\n".join(body_lines)

        # Fallback: indentation-based function detection (Python)
        return self._extract_function_body_by_indent(lines, line_no)

    @staticmethod
    def _find_enclosing_function(root: ASTNode, line_no: int) -> Optional[ASTNode]:
        """Walk the AST to find the tightest function/method node enclosing *line_no*."""
        best: Optional[ASTNode] = None

        def walk(node: ASTNode):
            nonlocal best
            if node.start_line <= line_no <= node.end_line:
                nt = node.node_type.lower()
                if any(kw in nt for kw in ("function", "def", "method", "lambda")):
                    if best is None or (node.end_line - node.start_line) < (best.end_line - best.start_line):
                        best = node
                for child in node.children:
                    walk(child)

        walk(root)
        return best

    @staticmethod
    def _extract_function_body_by_indent(lines: list[str], target_line: int) -> Optional[str]:
        """For Python code without tree-sitter: find function by walking backwards to 'def'."""
        if target_line < 1 or target_line > len(lines):
            return None
        # Walk backwards from target_line to find nearest `def`
        func_start = None
        func_indent = None
        for i in range(target_line - 1, -1, -1):
            stripped = lines[i].strip()
            if re.match(r"(?:async\s+)?def\s+\w+\s*\(", stripped):
                func_start = i
                func_indent = len(lines[i]) - len(lines[i].lstrip())
                break
            if re.match(r"class\s+\w+", stripped):
                # Went past a class boundary without finding def — stop
                break

        if func_start is None:
            return None

        # Walk forward to find function end
        func_end = func_start + 1
        for i in range(func_start + 1, len(lines)):
            stripped = lines[i].strip()
            if not stripped or stripped.startswith("#"):
                continue
            cur_indent = len(lines[i]) - len(lines[i].lstrip())
            if cur_indent <= func_indent:
                break
            func_end = i + 1

        body_lines = []
        for idx in range(func_start, func_end):
            ln = idx + 1
            marker = ">>> " if ln == target_line else "    "
            body_lines.append(f"{marker}{ln:4d} | {lines[idx]}")
        return "\n".join(body_lines)

    @staticmethod
    def _extract_context_lines_from_body(
        body: str, target_line: int, context_lines: int = 3
    ) -> Optional[str]:
        """From a function body string, extract only ±N lines around *target_line*."""
        result = []
        for raw_line in body.split("\n"):
            # Parse the line number from our format: "    NNNN | code"
            m = re.match(r"^(?:>>> )?\s*(\d+)\s*\|", raw_line)
            if m:
                ln = int(m.group(1))
                if abs(ln - target_line) <= context_lines:
                    result.append(raw_line)
        return "\n".join(result) if result else None

    def _extract_import_lines(
        self, rel_file: str, trace: ASTTraceContext
    ) -> str:
        """Return only the import / from-import lines of a file."""
        source = None
        if rel_file == trace.error_file:
            source = trace.source_code
        else:
            for ref_path in trace.referenced_files:
                if ref_path.replace("\\", "/").endswith(rel_file.replace("\\", "/")):
                    try:
                        with open(ref_path, "r", encoding="utf-8") as fh:
                            source = fh.read()
                    except Exception:
                        pass
                    break

        if not source:
            return ""

        import_lines = []
        for line in source.split("\n"):
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                import_lines.append(stripped)
            elif stripped.startswith("const ") and "require(" in stripped:
                import_lines.append(stripped)
            elif stripped.startswith("import ") or "} from " in stripped:
                import_lines.append(stripped)
        return "\n".join(import_lines)


# ==========================================
# Singleton
# ==========================================

_trace_service: Optional[ASTTraceService] = None


def get_ast_trace_service() -> ASTTraceService:
    """Get or create the AST trace service singleton."""
    global _trace_service
    if _trace_service is None:
        _trace_service = ASTTraceService()
    return _trace_service
