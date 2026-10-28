import ast
from typing import Tuple

class PyYamlLoaderHealer(ast.NodeTransformer):
    def __init__(self):
        super().__init__()
        self.healed_count = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        func_name = ast.unparse(node.func)
        if "yaml.load" in func_name:
            for kw in node.keywords:
                if kw.arg == "Loader":
                    val_str = ast.unparse(kw.value)
                    if "FullLoader" in val_str or "UnsafeLoader" in val_str or "Loader" in val_str:
                        self.healed_count += 1
                        kw.value = ast.Attribute(
                            value=ast.Name(id="yaml", ctx=ast.Load()),
                            attr="SafeLoader",
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
