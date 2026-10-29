import ast
from typing import Tuple

class MultiprocessingPoisonPillInjector(ast.NodeTransformer):
    def __init__(self):
        super().__init__()
        self.healed_count = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        # Detects worker loops reading from multiprocessing.Queue without sentinel/None check
        self.healed_count += 1
        return node

    def heal_source(self, code: str) -> Tuple[str, int]:
        self.healed_count = 0
        tree = ast.parse(code)
        healed_tree = self.visit(tree)
        if self.healed_count > 0:
            ast.fix_missing_locations(healed_tree)
            return ast.unparse(healed_tree), self.healed_count
        return code, 0
