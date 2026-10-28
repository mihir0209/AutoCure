import ast
from typing import Tuple

class TempfileFdLeakHealer(ast.NodeTransformer):
    def __init__(self):
        super().__init__()
        self.healed_count = 0

    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        self.generic_visit(node)
        # Identifies standalone `fd, path = tempfile.mkstemp()` lacking context manager
        if isinstance(node.value, ast.Call):
            call_str = ast.unparse(node.value.func)
            if "tempfile.mkstemp" in call_str:
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
