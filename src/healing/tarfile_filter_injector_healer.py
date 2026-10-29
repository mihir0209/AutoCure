import ast
from typing import Tuple

class TarfileFilterInjectorHealer(ast.NodeTransformer):
    def __init__(self):
        super().__init__()
        self.healed_count = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        func_name = ast.unparse(node.func)
        if "extractall" in func_name:
            has_filter = any(kw.arg == "filter" for kw in node.keywords)
            if not has_filter:
                self.healed_count += 1
                node.keywords.append(ast.keyword(arg="filter", value=ast.Constant(value="data")))
        return node

    def heal_source(self, code: str) -> Tuple[str, int]:
        self.healed_count = 0
        tree = ast.parse(code)
        healed_tree = self.visit(tree)
        if self.healed_count > 0:
            ast.fix_missing_locations(healed_tree)
            return ast.unparse(healed_tree), self.healed_count
        return code, 0
