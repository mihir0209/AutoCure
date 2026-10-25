"""Automated Invariant Guard & Bounds Clamping Synthesizer.

Detects risky arithmetic expressions prone to ZeroDivisionError and domain errors
(e.g., negative sqrt) and automatically synthesizes inline defensive clamp guards.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class InvariantViolationFinding:
    function_name: Optional[str]
    line_number: int
    invariant_type: str
    expression: str
    synthesized_guard: str


class InvariantGuardSynthesizer(ast.NodeTransformer):
    """Scans and transforms division and domain calls into guarded clamped forms."""

    def __init__(self) -> None:
        super().__init__()
        self.findings: List[InvariantViolationFinding] = []
        self._current_function: Optional[str] = None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        old_fn = self._current_function
        self._current_function = node.name
        self.generic_visit(node)
        self._current_function = old_fn
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        old_fn = self._current_function
        self._current_function = node.name
        self.generic_visit(node)
        self._current_function = old_fn
        return node

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        self.generic_visit(node)

        # Division: a / b or a // b or a % b
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)):
            # If denominator is a non-zero literal constant, it is safe
            if isinstance(node.right, ast.Constant) and node.right.value != 0:
                return node

            # If already guarded conditional, do not double-wrap
            if isinstance(node.right, ast.IfExp):
                return node

            orig_right_str = ast.unparse(node.right)

            # Synthesize: (right if right != 0 else 1.0)
            guarded_right = ast.IfExp(
                test=ast.Compare(
                    left=node.right,
                    ops=[ast.NotEq()],
                    comparators=[ast.Constant(value=0)],
                ),
                body=node.right,
                orelse=ast.Constant(value=1.0 if isinstance(node.op, ast.Div) else 1),
            )
            ast.copy_location(guarded_right, node.right)
            node.right = guarded_right

            self.findings.append(
                InvariantViolationFinding(
                    function_name=self._current_function,
                    line_number=node.lineno,
                    invariant_type="ZERO_DIVISION_GUARD",
                    expression=orig_right_str,
                    synthesized_guard=ast.unparse(guarded_right),
                )
            )

        return node

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)

        call_str = ast.unparse(node.func)
        # math.sqrt(x) -> math.sqrt(max(0.0, x))
        if call_str in ("math.sqrt", "sqrt") and len(node.args) == 1:
            arg = node.args[0]
            if not (isinstance(arg, ast.Call) and ast.unparse(arg.func) == "max"):
                orig_arg_str = ast.unparse(arg)
                clamped_arg = ast.Call(
                    func=ast.Name(id="max", ctx=ast.Load()),
                    args=[ast.Constant(value=0.0), arg],
                    keywords=[],
                )
                ast.copy_location(clamped_arg, arg)
                node.args[0] = clamped_arg

                self.findings.append(
                    InvariantViolationFinding(
                        function_name=self._current_function,
                        line_number=node.lineno,
                        invariant_type="NEGATIVE_SQRT_GUARD",
                        expression=orig_arg_str,
                        synthesized_guard=ast.unparse(clamped_arg),
                    )
                )

        return node


def synthesize_invariant_guards(
    source_code: str,
) -> Tuple[str, List[InvariantViolationFinding]]:
    """Transforms unguarded division and math expressions into resilient guarded forms."""
    tree = ast.parse(source_code)
    synthesizer = InvariantGuardSynthesizer()
    transformed = synthesizer.visit(tree)
    ast.fix_missing_locations(transformed)

    new_source = ast.unparse(transformed)
    compile(new_source, "<guarded_invariants>", mode="exec")
    return new_source, synthesizer.findings
