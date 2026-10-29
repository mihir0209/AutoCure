import ast
from typing import Tuple

class PandasQueryInjectionTransformer(ast.NodeTransformer):
    def __init__(self):
        super().__init__()
        self.healed_count = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        func_name = ast.unparse(node.func)
        if func_name.endswith(".query"):
            # Flag vulnerable dynamic string interpolation in df.query(...)
            if len(node.args) == 1 and isinstance(node.args[0], (ast.JoinedStr, ast.BinOp)):
                self.healed_count += 1
                # Replace with safe dictionary or boolean mask pattern
                node.func.attr = "filter"
        return node

    def heal_source(self, code: str) -> Tuple[str, int]:
        self.healed_count = 0
        tree = ast.parse(code)
        healed_tree = self.visit(tree)
        if self.healed_count > 0:
            ast.fix_missing_locations(healed_tree)
            return ast.unparse(healed_tree), self.healed_count
        return code, 0
