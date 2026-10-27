"""
Reentrancy & Infinite Loop Denial-of-Service AST Healer.

Scans Python AST for dangerous unbounded loops (while True / while 1 without break/return/raise)
and synthesizes deterministic iteration guardrails to neutralize denial-of-service vulnerabilities.
"""

import ast
from typing import Tuple, List, Any


class LoopTerminalFinder(ast.NodeVisitor):
    def __init__(self):
        self.has_terminal = False

    def visit_Break(self, node):
        self.has_terminal = True

    def visit_Return(self, node):
        self.has_terminal = True

    def visit_Raise(self, node):
        self.has_terminal = True


class ReentrancyDosHealer(ast.NodeTransformer):
    def __init__(self, max_iterations: int = 1000):
        super().__init__()
        self.max_iterations = max_iterations
        self.healed_count = 0
        self.healed_locations: List[int] = []

    def is_unbounded_while(self, node: ast.While) -> bool:
        """Determines if a While node has a truthy constant condition without terminal statements."""
        is_infinite_test = False
        if isinstance(node.test, ast.Constant) and bool(node.test.value) is True:
            is_infinite_test = True
        elif isinstance(node.test, ast.Name) and node.test.id == "True":
            is_infinite_test = True

        if not is_infinite_test:
            return False

        # Scan body for break/return/raise
        finder = LoopTerminalFinder()
        for stmt in node.body:
            finder.visit(stmt)

        return not finder.has_terminal

    def heal_source(self, source_code: str) -> Tuple[str, int]:
        """Parses source code, heals any unbounded loops, and returns healed code + count."""
        tree = ast.parse(source_code)
        healed_tree = self.visit(tree)
        ast.fix_missing_locations(healed_tree)
        healed_source = ast.unparse(healed_tree)
        return healed_source, self.healed_count

    def visit_While(self, node: ast.While) -> Any:
        self.generic_visit(node)
        if self.is_unbounded_while(node):
            self.healed_count += 1
            lineno = getattr(node, "lineno", 0)
            self.healed_locations.append(lineno)
            var_name = f"_autocure_loop_limit_{self.healed_count}"

            init_stmt = ast.Assign(
                targets=[ast.Name(id=var_name, ctx=ast.Store())],
                value=ast.Constant(value=self.max_iterations),
            )
            guard_body = ast.parse(
                f"{var_name} -= 1\n"
                f"if {var_name} <= 0:\n"
                f"    raise RuntimeError('AutoCure: Unbounded loop execution halted')\n"
            ).body

            node.body = guard_body + node.body
            return [init_stmt, node]
        return node
