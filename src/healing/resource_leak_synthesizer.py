"""Automated Resource Leak & Context Manager Synthesizer.

Detects unmanaged resource allocations (raw open, socket, client connections)
and synthesizes proper Python 'with' context managers or try-finally close guards.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any


@dataclass
class ResourceLeakFinding:
    line_number: int
    variable_name: str
    allocation_expression: str
    remediation_kind: str


class ResourceLeakSynthesizer(ast.NodeTransformer):
    """AST Transformer converting raw open() calls into 'with' context manager blocks."""

    RESOURCE_CALL_NAMES = {"open", "connect", "create_connection", "socket"}

    def __init__(self) -> None:
        self.findings: list[ResourceLeakFinding] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        new_body: list[ast.stmt] = []
        i = 0
        while i < len(node.body):
            stmt = node.body[i]

            # Check for: var = open(...)
            if (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and isinstance(stmt.value, ast.Call)
            ):
                call = stmt.value
                func_name = ""
                if isinstance(call.func, ast.Name):
                    func_name = call.func.id
                elif isinstance(call.func, ast.Attribute):
                    func_name = call.func.attr

                if func_name in self.RESOURCE_CALL_NAMES:
                    var_name = stmt.targets[0].id
                    rest_of_body = node.body[i + 1:]

                    # Synthesize: with <call> as <var_name>: ...
                    with_stmt = ast.With(
                        items=[
                            ast.withitem(
                                context_expr=call,
                                optional_vars=ast.Name(id=var_name, ctx=ast.Store()),
                            )
                        ],
                        body=rest_of_body if rest_of_body else [ast.Pass()],
                    )
                    ast.copy_location(with_stmt, stmt)
                    self.findings.append(
                        ResourceLeakFinding(
                            line_number=getattr(stmt, "lineno", 1),
                            variable_name=var_name,
                            allocation_expression=ast.unparse(call),
                            remediation_kind="WITH_CONTEXT_SYNTHESIS",
                        )
                    )
                    new_body.append(with_stmt)
                    break

            new_body.append(self.visit(stmt))
            i += 1

        node.body = new_body
        return node


def synthesize_resource_management(source_code: str) -> tuple[str, list[ResourceLeakFinding]]:
    """Transforms raw resource allocations into safe context managers."""
    tree = ast.parse(source_code)
    synthesizer = ResourceLeakSynthesizer()
    transformed_tree = synthesizer.visit(tree)
    ast.fix_missing_locations(transformed_tree)

    new_code = ast.unparse(transformed_tree)
    compile(new_code, "<synthesized>", "exec")
    return new_code, synthesizer.findings
