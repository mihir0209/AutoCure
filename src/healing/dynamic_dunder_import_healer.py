import ast
from typing import Tuple

class DynamicDunderImportHealer(ast.NodeTransformer):
    def __init__(self):
        super().__init__()
        self.healed_count = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        func_name = ast.unparse(node.func)
        if func_name == "__import__":
            self.healed_count += 1
            # Replace with importlib.import_module
            node.func = ast.Attribute(
                value=ast.Name(id="importlib", ctx=ast.Load()),
                attr="import_module",
                ctx=ast.Load()
            )
        return node

    def heal_source(self, code: str) -> Tuple[str, int]:
        self.healed_count = 0
        tree = ast.parse(code)
        healed_tree = self.visit(tree)
        if self.healed_count > 0:
            ast.fix_missing_locations(healed_tree)
            return ast.unparse(healed_tree), self.healed_count
        return code, 0
