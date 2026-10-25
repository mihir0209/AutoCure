"""Unclosed Network Session & ThreadPoolExecutor Sanitizer for AutoCure.

Detects bare instantiation of thread/process executors and network client sessions
(e.g. ThreadPoolExecutor, ProcessPoolExecutor, requests.Session, aiohttp.ClientSession)
that lack explicit cleanup or context managers, and wraps them in safe `with` blocks.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class ExecutorSessionFinding:
    resource_type: str  # "ThreadPoolExecutor", "ProcessPoolExecutor", "Session", "ClientSession"
    variable_name: str
    line_number: int
    enclosing_function: str


class ExecutorSessionVisitor(ast.NodeVisitor):
    """Detects bare session or executor assignments lacking context managers."""

    TARGET_CONSTRUCTORS = {
        "ThreadPoolExecutor",
        "ProcessPoolExecutor",
        "Session",
        "ClientSession",
        "PoolManager",
    }

    def __init__(self) -> None:
        self.findings: List[ExecutorSessionFinding] = []
        self.current_function: Optional[str] = None
        self.with_assigned_targets: set[str] = set()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        prev_fn = self.current_function
        self.current_function = node.name

        # Check existing with statements in function
        for stmt in node.body:
            if isinstance(stmt, ast.With):
                for item in stmt.items:
                    if item.optional_vars and isinstance(item.optional_vars, ast.Name):
                        self.with_assigned_targets.add(item.optional_vars.id)

        # Inspect statement assignments
        for stmt in node.body:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                var_name = stmt.targets[0].id
                if var_name not in self.with_assigned_targets:
                    ctor_name = self._extract_constructor_name(stmt.value)
                    if ctor_name in self.TARGET_CONSTRUCTORS:
                        self.findings.append(
                            ExecutorSessionFinding(
                                resource_type=ctor_name,
                                variable_name=var_name,
                                line_number=stmt.lineno,
                                enclosing_function=node.name,
                            )
                        )

        self.current_function = prev_fn

    visit_AsyncFunctionDef = visit_FunctionDef

    def _extract_constructor_name(self, node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                return node.func.id
            elif isinstance(node.func, ast.Attribute):
                return node.func.attr
        return None


class ExecutorSessionTransformer(ast.NodeTransformer):
    """Wraps bare executor/session assignments into with statements."""

    def __init__(self, findings: List[ExecutorSessionFinding]) -> None:
        self.findings = findings

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        self.generic_visit(node)
        fn_findings = [f for f in self.findings if f.enclosing_function == node.name]
        if not fn_findings:
            return node

        finding = fn_findings[0]

        # Find the assignment statement index
        target_idx = -1
        for idx, stmt in enumerate(node.body):
            if isinstance(stmt, ast.Assign) and stmt.lineno == finding.line_number:
                target_idx = idx
                break

        if target_idx != -1:
            assign_stmt = node.body[target_idx]
            call_expr = assign_stmt.value
            remaining_stmts = node.body[target_idx + 1 :]

            if remaining_stmts:
                with_stmt = ast.With(
                    items=[
                        ast.withitem(
                            context_expr=call_expr,
                            optional_vars=ast.Name(id=finding.variable_name, ctx=ast.Store()),
                        )
                    ],
                    body=remaining_stmts,
                )
                node.body = node.body[:target_idx] + [with_stmt]

        return node

    visit_AsyncFunctionDef = visit_FunctionDef


class ExecutorSessionSanitizer:
    """Orchestrator for executor and session cleanup sanitization."""

    def analyze(self, source_code: str) -> List[ExecutorSessionFinding]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return []
        visitor = ExecutorSessionVisitor()
        visitor.visit(tree)
        return visitor.findings

    def sanitize(self, source_code: str) -> Tuple[str, List[ExecutorSessionFinding]]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return source_code, []

        visitor = ExecutorSessionVisitor()
        visitor.visit(tree)
        if not visitor.findings:
            return source_code, []

        transformer = ExecutorSessionTransformer(visitor.findings)
        modified_tree = transformer.visit(tree)
        ast.fix_missing_locations(modified_tree)

        try:
            new_code = ast.unparse(modified_tree)
            compile(new_code, "<healed_executor>", "exec")
            return new_code, visitor.findings
        except Exception:
            return source_code, visitor.findings


def sanitize_executor_sessions(source_code: str) -> Tuple[str, List[ExecutorSessionFinding]]:
    engine = ExecutorSessionSanitizer()
    return engine.sanitize(source_code)
