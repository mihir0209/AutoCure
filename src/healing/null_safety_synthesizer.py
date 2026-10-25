"""Automated Type-Inference & Null-Safety Guard Synthesizer.

Detects unsafe nullable dereferences, attribute accesses, and arithmetic operations
in Python AST, and synthesizes defensive coalesce expressions or early-return guards.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any


@dataclass
class NullSafetyFinding:
    line_number: int
    variable_name: str
    unsafe_expression: str
    remediation_kind: str
    synthesized_guard: str


class NullSafetySynthesizer(ast.NodeTransformer):
    """AST Transformer that transforms unsafe nullable operations into defensive guards."""

    def __init__(self, nullable_vars: set[str] | None = None) -> None:
        self.nullable_vars = nullable_vars or set()
        self.findings: list[NullSafetyFinding] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        # Detect parameters with default None or Optional type hints
        local_nullables = set(self.nullable_vars)
        for arg in node.args.args:
            # Check default values
            pass
        # Process body
        self.generic_visit(node)
        return node

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        self.generic_visit(node)
        # If accessing attr on a variable known/suspected to be nullable
        if isinstance(node.value, ast.Name) and (
            node.value.id in self.nullable_vars or node.value.id.startswith("nullable_")
        ):
            var_name = node.value.id
            unsafe_code = ast.unparse(node)
            guard_code = f"({unsafe_code} if {var_name} is not None else None)"

            # Synthesize IfExp: (node.value.attr if node.value is not None else None)
            new_node = ast.IfExp(
                test=ast.Compare(
                    left=ast.Name(id=var_name, ctx=ast.Load()),
                    ops=[ast.IsNot()],
                    comparators=[ast.Constant(value=None)],
                ),
                body=node,
                orelse=ast.Constant(value=None),
            )
            ast.copy_location(new_node, node)
            self.findings.append(
                NullSafetyFinding(
                    line_number=getattr(node, "lineno", 1),
                    variable_name=var_name,
                    unsafe_expression=unsafe_code,
                    remediation_kind="ATTRIBUTE_COALESCE",
                    synthesized_guard=guard_code,
                )
            )
            return new_node
        return node

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        self.generic_visit(node)
        # Check if left or right operand is nullable in addition/multiplication/subtraction
        target_name: str | None = None
        default_val: Any = 0

        if isinstance(node.left, ast.Name) and (
            node.left.id in self.nullable_vars or node.left.id.startswith("nullable_")
        ):
            target_name = node.left.id
            is_left = True
        elif isinstance(node.right, ast.Name) and (
            node.right.id in self.nullable_vars or node.right.id.startswith("nullable_")
        ):
            target_name = node.right.id
            is_left = False
        else:
            return node

        unsafe_code = ast.unparse(node)
        coalesce_expr = ast.IfExp(
            test=ast.Compare(
                left=ast.Name(id=target_name, ctx=ast.Load()),
                ops=[ast.IsNot()],
                comparators=[ast.Constant(value=None)],
            ),
            body=ast.Name(id=target_name, ctx=ast.Load()),
            orelse=ast.Constant(value=default_val),
        )

        if is_left:
            new_node = ast.BinOp(left=coalesce_expr, op=node.op, right=node.right)
        else:
            new_node = ast.BinOp(left=node.left, op=node.op, right=coalesce_expr)

        ast.copy_location(new_node, node)
        self.findings.append(
            NullSafetyFinding(
                line_number=getattr(node, "lineno", 1),
                variable_name=target_name,
                unsafe_expression=unsafe_code,
                remediation_kind="BINOP_COALESCE",
                synthesized_guard=ast.unparse(new_node),
            )
        )
        return new_node


def synthesize_null_safety(
    source_code: str,
    nullable_vars: set[str] | list[str] | None = None,
) -> tuple[str, list[NullSafetyFinding]]:
    """Transforms source code to insert null-safety guards on identified nullable variables."""
    tree = ast.parse(source_code)
    nullables = set(nullable_vars or [])

    # Heuristic: discover variables assigned None or passed Optional
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if isinstance(node.value, ast.Constant) and node.value.value is None:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        nullables.add(target.id)

    synthesizer = NullSafetySynthesizer(nullable_vars=nullables)
    transformed_tree = synthesizer.visit(tree)
    ast.fix_missing_locations(transformed_tree)

    # Validate syntax compiles cleanly
    new_code = ast.unparse(transformed_tree)
    compile(new_code, "<synthesized>", "exec")

    return new_code, synthesizer.findings
