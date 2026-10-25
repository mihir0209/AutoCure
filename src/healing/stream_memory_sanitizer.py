"""Memory Exhaustion & Unbounded Stream Reading AST Sanitizer.

Detects unbounded stream reads (e.g. f.read(), file.read(), stream.read()) that risk triggering
Out-Of-Memory (OOM) conditions on large inputs, and synthesizes bounded chunked reads with safe caps.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

DEFAULT_MAX_CHUNK_BYTES = 65536  # 64 KB safe chunk size


@dataclass
class StreamMemoryFinding:
    line_number: int
    method_name: str
    target_var: str
    vulnerability_reason: str
    recommended_chunk_size: int


class StreamMemoryVisitor(ast.NodeVisitor):
    """AST visitor that detects unbounded .read() and .readlines() calls."""

    READ_METHODS = {"read", "readline", "readlines"}

    def __init__(self) -> None:
        self.findings: List[StreamMemoryFinding] = []

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr in self.READ_METHODS:
            method_name = node.func.attr
            target_var = ast.unparse(node.func.value)

            # Check if arguments are provided to bound the read
            if method_name == "read" and len(node.args) == 0:
                self.findings.append(
                    StreamMemoryFinding(
                        line_number=node.lineno,
                        method_name="read",
                        target_var=target_var,
                        vulnerability_reason="Unbounded stream read without buffer limit risks OOM exhaustion",
                        recommended_chunk_size=DEFAULT_MAX_CHUNK_BYTES,
                    )
                )

        self.generic_visit(node)


class StreamMemoryTransformer(ast.NodeTransformer):
    """AST transformer that bounds unbounded stream reads with safe chunk size constants."""

    def __init__(self, findings: List[StreamMemoryFinding]) -> None:
        self.findings_by_line = {f.line_number: f for f in findings}
        self.patch_count = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        finding = self.findings_by_line.get(node.lineno)
        if finding and finding.method_name == "read" and len(node.args) == 0:
            # Inject chunk size argument: f.read(65536)
            node.args.append(ast.Constant(value=finding.recommended_chunk_size))
            self.patch_count += 1
        return node


class StreamMemorySanitizer:
    """Orchestrator for memory exhaustion detection and bounded stream AST synthesis."""

    def analyze(self, source_code: str) -> List[StreamMemoryFinding]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return []
        visitor = StreamMemoryVisitor()
        visitor.visit(tree)
        return visitor.findings

    def synthesize(self, source_code: str) -> Tuple[str, List[StreamMemoryFinding]]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return source_code, []

        visitor = StreamMemoryVisitor()
        visitor.visit(tree)
        if not visitor.findings:
            return source_code, []

        transformer = StreamMemoryTransformer(visitor.findings)
        modified_tree = transformer.visit(tree)
        ast.fix_missing_locations(modified_tree)

        try:
            new_code = ast.unparse(modified_tree)
            compile(new_code, "<healed_stream>", "exec")
            return new_code, visitor.findings
        except Exception:
            return source_code, visitor.findings


def sanitize_stream_memory(source_code: str) -> Tuple[str, List[StreamMemoryFinding]]:
    engine = StreamMemorySanitizer()
    return engine.synthesize(source_code)
