import ast
from typing import Tuple

class ShelveMarshalDefusalHealer(ast.NodeTransformer):
    DANGEROUS_MODULES = {"shelve", "marshal"}

    def __init__(self):
        super().__init__()
        self.healed_count = 0

    def visit_Import(self, node: ast.Import) -> ast.AST:
        for alias in node.names:
            if alias.name in self.DANGEROUS_MODULES:
                self.healed_count += 1
                alias.name = "json" # Rewrite to safe json serializer
        return node

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        func_name = ast.unparse(node.func)
        if "marshal.loads" in func_name:
            self.healed_count += 1
            node.func = ast.Attribute(value=ast.Name(id="json", ctx=ast.Load()), attr="loads", ctx=ast.Load())
        return node

    def heal_source(self, code: str) -> Tuple[str, int]:
        self.healed_count = 0
        tree = ast.parse(code)
        healed_tree = self.visit(tree)
        if self.healed_count > 0:
            ast.fix_missing_locations(healed_tree)
            return ast.unparse(healed_tree), self.healed_count
        return code, 0
