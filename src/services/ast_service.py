"""
AST Service for the Self-Healing Software System v2.0

Provides AST (Abstract Syntax Tree) building and analysis using tree-sitter.
Used for:
- Building AST from source code files
- Tracing error locations to specific AST nodes
- Extracting context around error nodes (parent functions, classes, etc.)
- Generating interactive AST visualizations for emails
"""

import os
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from dataclasses import dataclass

from utils.models import ASTNode, ASTContext, ASTVisualization
from utils.logger import setup_colored_logger


logger = setup_colored_logger("ast_service")


# Try to import tree-sitter
try:
    import tree_sitter
    from tree_sitter import Language, Parser
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    logger.warning("tree-sitter not installed. AST features will be limited.")


class ASTService:
    """
    Service for building and analyzing ASTs using tree-sitter.
    
    Supports multiple languages:
    - JavaScript/TypeScript
    - Python
    - Java
    - More can be added by installing tree-sitter language grammars
    """
    
    # Language to file extension mapping
    LANGUAGE_EXTENSIONS = {
        "javascript": [".js", ".jsx", ".mjs", ".cjs"],
        "typescript": [".ts", ".tsx"],
        "python": [".py", ".pyw"],
        "java": [".java"],
        "go": [".go"],
        "rust": [".rs"],
        "c": [".c", ".h"],
        "cpp": [".cpp", ".cc", ".cxx", ".hpp", ".hh"],
    }
    
    def __init__(self, languages_path: Optional[Path] = None):
        """
        Initialize the AST service.
        
        Args:
            languages_path: Path to compiled language libraries for tree-sitter
        """
        self.parsers: Dict[str, Any] = {}
        self.languages_path = languages_path
        
        if TREE_SITTER_AVAILABLE:
            self._initialize_parsers()
        else:
            logger.warning("AST parsing disabled - install tree-sitter for full functionality")
    
    def _initialize_parsers(self):
        """Initialize tree-sitter parsers for supported languages."""
        # Note: In a real implementation, you would compile and load language grammars
        # For now, we'll use a fallback approach
        pass
    
    def detect_language(self, file_path: str) -> Optional[str]:
        """Detect the programming language from file extension."""
        ext = Path(file_path).suffix.lower()
        
        for language, extensions in self.LANGUAGE_EXTENSIONS.items():
            if ext in extensions:
                return language
        
        return None
    
    def parse_file(self, file_path: str) -> Optional[ASTNode]:
        """
        Parse a file and return its AST root node.
        
        Args:
            file_path: Path to the source file
            
        Returns:
            Root ASTNode or None if parsing fails
        """
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return None
        
        language = self.detect_language(file_path)
        if not language:
            logger.warning(f"Unknown language for file: {file_path}")
            return None
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source_code = f.read()
            
            return self.parse_code(source_code, language, file_path)
            
        except Exception as e:
            logger.error(f"Error parsing file {file_path}: {e}")
            return None
    
    def parse_code(
        self, source_code: str, language: str, file_path: Optional[str] = None
    ) -> Optional[ASTNode]:
        """
        Parse source code and return its AST root node.
        
        This is a fallback implementation using regex-based parsing
        when tree-sitter is not available.
        """
        if TREE_SITTER_AVAILABLE and language in self.parsers:
            return self._parse_with_tree_sitter(source_code, language, file_path)
        else:
            return self._parse_fallback(source_code, language, file_path)
    
    def _parse_with_tree_sitter(
        self, source_code: str, language: str, file_path: Optional[str]
    ) -> Optional[ASTNode]:
        """Parse using tree-sitter (when available)."""
        # This would be the tree-sitter implementation
        # For now, fall back to regex-based parsing
        return self._parse_fallback(source_code, language, file_path)
    
    def _parse_fallback(
        self, source_code: str, language: str, file_path: Optional[str]
    ) -> Optional[ASTNode]:
        """
        Fallback AST parsing using regex for basic structure extraction.
        
        This extracts functions, classes, and methods - enough for context building.
        """
        lines = source_code.split("\n")
        
        if language in ["javascript", "typescript"]:
            return self._parse_javascript_fallback(lines, file_path)
        elif language == "python":
            return self._parse_python_fallback(lines, file_path)
        elif language == "java":
            return self._parse_java_fallback(lines, file_path)
        else:
            # Generic fallback - just create a root node
            return ASTNode(
                node_type="source_file",
                name=file_path or "unknown",
                start_line=1,
                end_line=len(lines),
                children=[],
                source_text=source_code[:1000],  # First 1000 chars
            )
    
    def _parse_javascript_fallback(
        self, lines: List[str], file_path: Optional[str]
    ) -> ASTNode:
        """Parse JavaScript/TypeScript using regex."""
        import re
        
        children = []
        
        # Pattern for functions
        func_patterns = [
            r"^\s*(?:async\s+)?function\s+(\w+)\s*\(",  # function name()
            r"^\s*(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(",  # const name = (
            r"^\s*(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?function",  # const name = function
            r"^\s*(\w+)\s*:\s*(?:async\s+)?function",  # name: function (in object)
            r"^\s*(?:async\s+)?(\w+)\s*\([^)]*\)\s*{",  # method name() { in class
        ]
        
        # Pattern for classes
        class_pattern = r"^\s*class\s+(\w+)"
        
        # Pattern for exports
        export_pattern = r"^\s*(?:module\.)?exports\s*[.=]"
        
        for i, line in enumerate(lines, 1):
            # Check for class
            class_match = re.match(class_pattern, line)
            if class_match:
                children.append(ASTNode(
                    node_type="class_declaration",
                    name=class_match.group(1),
                    start_line=i,
                    end_line=i,  # Will be updated
                    children=[],
                ))
                continue
            
            # Check for functions
            for pattern in func_patterns:
                func_match = re.match(pattern, line)
                if func_match:
                    children.append(ASTNode(
                        node_type="function_declaration",
                        name=func_match.group(1),
                        start_line=i,
                        end_line=i,
                        children=[],
                    ))
                    break
        
        return ASTNode(
            node_type="source_file",
            name=file_path or "unknown.js",
            start_line=1,
            end_line=len(lines),
            children=children,
        )
    
    def _parse_python_fallback(
        self, lines: List[str], file_path: Optional[str]
    ) -> ASTNode:
        """Parse Python using regex."""
        import re
        
        children = []
        
        func_pattern = r"^\s*(?:async\s+)?def\s+(\w+)\s*\("
        class_pattern = r"^\s*class\s+(\w+)"
        
        for i, line in enumerate(lines, 1):
            # Check for class
            class_match = re.match(class_pattern, line)
            if class_match:
                children.append(ASTNode(
                    node_type="class_definition",
                    name=class_match.group(1),
                    start_line=i,
                    end_line=i,
                    children=[],
                ))
                continue
            
            # Check for function
            func_match = re.match(func_pattern, line)
            if func_match:
                children.append(ASTNode(
                    node_type="function_definition",
                    name=func_match.group(1),
                    start_line=i,
                    end_line=i,
                    children=[],
                ))
        
        return ASTNode(
            node_type="module",
            name=file_path or "unknown.py",
            start_line=1,
            end_line=len(lines),
            children=children,
        )
    
    def _parse_java_fallback(
        self, lines: List[str], file_path: Optional[str]
    ) -> ASTNode:
        """Parse Java using regex."""
        import re
        
        children = []
        
        class_pattern = r"^\s*(?:public|private|protected)?\s*(?:abstract|final)?\s*class\s+(\w+)"
        method_pattern = r"^\s*(?:public|private|protected)?\s*(?:static)?\s*(?:\w+)\s+(\w+)\s*\("
        
        for i, line in enumerate(lines, 1):
            class_match = re.match(class_pattern, line)
            if class_match:
                children.append(ASTNode(
                    node_type="class_declaration",
                    name=class_match.group(1),
                    start_line=i,
                    end_line=i,
                    children=[],
                ))
                continue
            
            method_match = re.match(method_pattern, line)
            if method_match:
                children.append(ASTNode(
                    node_type="method_declaration",
                    name=method_match.group(1),
                    start_line=i,
                    end_line=i,
                    children=[],
                ))
        
        return ASTNode(
            node_type="compilation_unit",
            name=file_path or "Unknown.java",
            start_line=1,
            end_line=len(lines),
            children=children,
        )
    
    def find_node_at_line(
        self, root: ASTNode, line_number: int
    ) -> Optional[ASTNode]:
        """Find the most specific AST node containing the given line."""
        
        if not (root.start_line <= line_number <= root.end_line):
            return None
        
        # Check children first for more specific match
        for child in root.children:
            result = self.find_node_at_line(child, line_number)
            if result:
                return result
        
        # Return this node if it contains the line
        return root
    
    def get_context(
        self, root: ASTNode, line_number: int, context_lines: int = 10
    ) -> ASTContext:
        """
        Get context information for a specific line in the AST.
        
        Returns information about:
        - The containing function/method
        - The containing class
        - Surrounding code
        """
        node = self.find_node_at_line(root, line_number)
        
        # Find parent function
        parent_function = None
        parent_class = None
        
        def find_parents(n: ASTNode, path: List[ASTNode] = None):
            nonlocal parent_function, parent_class
            path = path or []
            
            if n.start_line <= line_number <= n.end_line:
                if n.node_type in ["function_declaration", "function_definition", 
                                   "method_declaration", "method_definition"]:
                    parent_function = n
                elif n.node_type in ["class_declaration", "class_definition"]:
                    parent_class = n
                
                for child in n.children:
                    find_parents(child, path + [n])
        
        find_parents(root)
        
        return ASTContext(
            error_node=node,
            parent_function=parent_function,
            parent_class=parent_class,
            context_start_line=max(1, line_number - context_lines),
            context_end_line=line_number + context_lines,
            sibling_nodes=[],
            imports=[],
        )
    
    def generate_visualization(
        self, root: ASTNode, error_line: Optional[int] = None, max_depth: int = 4
    ) -> ASTVisualization:
        """
        Generate an SVG visualization of the AST for email display.
        
        The visualization is interactive - nodes can be clicked to expand/collapse.
        Error nodes are highlighted.
        """
        svg_content = self._generate_svg(root, error_line, max_depth)
        
        return ASTVisualization(
            svg_content=svg_content,
            root_node=root,
            highlighted_line=error_line,
            interactive=True,
        )
    
    def _generate_svg(
        self, root: ASTNode, error_line: Optional[int], max_depth: int
    ) -> str:
        """Generate SVG content for AST visualization."""
        
        # Calculate dimensions
        width = 800
        node_height = 40
        indent = 30
        
        nodes_data = []
        
        def collect_nodes(node: ASTNode, depth: int = 0, y_offset: int = 0):
            if depth > max_depth:
                return y_offset
            
            is_error = (error_line and 
                       node.start_line <= error_line <= node.end_line)
            
            nodes_data.append({
                "node": node,
                "depth": depth,
                "y": y_offset,
                "is_error": is_error,
            })
            
            y = y_offset + node_height
            
            for child in node.children[:10]:  # Limit children
                y = collect_nodes(child, depth + 1, y)
            
            return y
        
        total_height = collect_nodes(root)
        
        # Build SVG
        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {total_height + 20}" '
            f'style="font-family: monospace; font-size: 12px;">',
            '<style>',
            '.node { cursor: pointer; }',
            '.node:hover rect { fill: #e0e0e0; }',
            '.error-node rect { fill: #ffcccc !important; stroke: #ff0000; stroke-width: 2; }',
            '.node-text { pointer-events: none; }',
            '</style>',
        ]
        
        for data in nodes_data:
            node = data["node"]
            x = data["depth"] * indent + 10
            y = data["y"] + 10
            is_error = data["is_error"]
            
            # Node rectangle
            rect_class = "error-node" if is_error else ""
            svg_parts.append(
                f'<g class="node {rect_class}" data-line="{node.start_line}">'
                f'<rect x="{x}" y="{y}" width="{width - x - 20}" height="{node_height - 5}" '
                f'fill="#f0f0f0" rx="3" />'
                f'<text class="node-text" x="{x + 5}" y="{y + 20}">'
                f'{node.node_type}: {node.name or ""} (L{node.start_line})'
                f'</text>'
                f'</g>'
            )
        
        svg_parts.append('</svg>')
        
        return "\n".join(svg_parts)


# Singleton instance
_ast_service: Optional[ASTService] = None


def get_ast_service() -> ASTService:
    """Get or create the AST service singleton."""
    global _ast_service
    if _ast_service is None:
        _ast_service = ASTService()
    return _ast_service
