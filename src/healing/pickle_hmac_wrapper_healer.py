import ast
from typing import Tuple

class PickleHmacWrapperHealer(ast.NodeTransformer):
    def __init__(self):
        super().__init__()
        self.healed_count = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        func_name = ast.unparse(node.func)
        if func_name in ("pickle.loads", "pickle.load", "_pickle.loads"):
            self.healed_count += 1
            # Wrap or rewrite to safe json.loads or authenticated loader
            node.func = ast.Attribute(
                value=ast.Name(id="json", ctx=ast.Load()),
                attr="loads",
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
