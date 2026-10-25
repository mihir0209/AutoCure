"""Circular Dependency & Module Import Cycle Break Synthesizer for AutoCure.

Analyzes module-level import statements that introduce circular dependencies.
Synthesizes lazy local imports inside consuming functions or places type-only annotations
under `if typing.TYPE_CHECKING:` guards to prevent partially initialized module errors.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class ImportCycleFinding:
    module_name: str
    symbol_name: Optional[str]
    line_number: int
    resolution_strategy: str  # "type_checking_guard" | "lazy_local_import"
    target_function: Optional[str] = None


class UsageVisitor(ast.NodeVisitor):
    """Classifies how an imported symbol is referenced: type annotation only vs runtime call/access."""

    def __init__(self, target_symbol: str) -> None:
        self.target_symbol = target_symbol
        self.in_annotation = False
        self.runtime_usages: List[ast.AST] = []
        self.annotation_usages: List[ast.AST] = []
        self.current_function: Optional[str] = None
        self.function_usages: Dict[str, List[ast.AST]] = {}

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        prev_fn = self.current_function
        self.current_function = node.name

        # Visit return annotation
        if node.returns:
            self.in_annotation = True
            self.visit(node.returns)
            self.in_annotation = False

        # Visit argument annotations
        for arg in node.args.args + node.args.kwonlyargs:
            if arg.annotation:
                self.in_annotation = True
                self.visit(arg.annotation)
                self.in_annotation = False

        # Visit function body
        for stmt in node.body:
            self.visit(stmt)

        self.current_function = prev_fn

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.in_annotation = True
        self.visit(node.annotation)
        self.in_annotation = False
        if node.value:
            self.visit(node.value)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id == self.target_symbol:
            if self.in_annotation:
                self.annotation_usages.append(node)
            else:
                self.runtime_usages.append(node)
                if self.current_function:
                    self.function_usages.setdefault(self.current_function, []).append(node)
        self.generic_visit(node)


class ImportCycleSynthesizer:
    """Detects and refactors circular import statements."""

    def break_cycle(
        self,
        source_code: str,
        cycle_module: str,
        cycle_symbol: Optional[str] = None,
    ) -> Tuple[str, List[ImportCycleFinding]]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return source_code, []

        target_sym = cycle_symbol or cycle_module
        usage_visitor = UsageVisitor(target_sym)
        usage_visitor.visit(tree)

        # Locate the import statement
        target_import_node: Optional[ast.stmt] = None
        for stmt in tree.body:
            if isinstance(stmt, ast.ImportFrom) and stmt.module and cycle_module in stmt.module:
                if not cycle_symbol or any(alias.name == cycle_symbol for alias in stmt.names):
                    target_import_node = stmt
                    break
            elif isinstance(stmt, ast.Import):
                if any(alias.name == cycle_module for alias in stmt.names):
                    target_import_node = stmt
                    break

        if not target_import_node:
            return source_code, []

        findings: List[ImportCycleFinding] = []

        # Strategy 1: Symbol only used in type annotations -> Wrap under `if TYPE_CHECKING:`
        if usage_visitor.annotation_usages and not usage_visitor.runtime_usages:
            findings.append(
                ImportCycleFinding(
                    module_name=cycle_module,
                    symbol_name=cycle_symbol,
                    line_number=target_import_node.lineno,
                    resolution_strategy="type_checking_guard",
                )
            )

            # Check if TYPE_CHECKING is already imported
            has_type_checking = any(
                isinstance(s, ast.ImportFrom)
                and s.module == "typing"
                and any(alias.name == "TYPE_CHECKING" for alias in s.names)
                for s in tree.body
            )

            new_body: List[ast.stmt] = []
            if not has_type_checking:
                tc_import = ast.ImportFrom(
                    module="typing",
                    names=[ast.alias(name="TYPE_CHECKING", asname=None)],
                    level=0,
                )
                new_body.append(tc_import)

            # Build `if TYPE_CHECKING: <import>`
            if_guard = ast.If(
                test=ast.Name(id="TYPE_CHECKING", ctx=ast.Load()),
                body=[target_import_node],
                orelse=[],
            )

            for s in tree.body:
                if s == target_import_node:
                    new_body.append(if_guard)
                else:
                    new_body.append(s)

            tree.body = new_body

        # Strategy 2: Symbol used inside specific function -> Relocate to lazy local import
        elif usage_visitor.function_usages and len(usage_visitor.function_usages) == 1:
            fn_name = next(iter(usage_visitor.function_usages.keys()))
            findings.append(
                ImportCycleFinding(
                    module_name=cycle_module,
                    symbol_name=cycle_symbol,
                    line_number=target_import_node.lineno,
                    resolution_strategy="lazy_local_import",
                    target_function=fn_name,
                )
            )

            # Remove from module top-level
            tree.body = [s for s in tree.body if s != target_import_node]

            # Insert at beginning of target function
            for s in tree.body:
                if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)) and s.name == fn_name:
                    s.body.insert(0, target_import_node)
                    break

        ast.fix_missing_locations(tree)
        try:
            new_code = ast.unparse(tree)
            compile(new_code, "<healed_import>", "exec")
            return new_code, findings
        except Exception:
            return source_code, findings


def synthesize_import_cycle_break(
    source_code: str,
    cycle_module: str,
    cycle_symbol: Optional[str] = None,
) -> Tuple[str, List[ImportCycleFinding]]:
    engine = ImportCycleSynthesizer()
    return engine.break_cycle(source_code, cycle_module, cycle_symbol)
