import ast
from typing import Tuple

class RsaKeyLengthHealer(ast.NodeTransformer):
    def __init__(self):
        super().__init__()
        self.healed_count = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        func_name = ast.unparse(node.func)
        if "RSA.generate" in func_name or "generate_private_key" in func_name:
            for idx, arg in enumerate(node.args):
                if isinstance(arg, ast.Constant) and isinstance(arg.value, int) and arg.value < 2048:
                    self.healed_count += 1
                    node.args[idx] = ast.Constant(value=3072)
            for kw in node.keywords:
                if kw.arg in ("bits", "key_size") and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, int) and kw.value.value < 2048:
                    self.healed_count += 1
                    kw.value = ast.Constant(value=3072)
        return node

    def heal_source(self, code: str) -> Tuple[str, int]:
        self.healed_count = 0
        tree = ast.parse(code)
        healed_tree = self.visit(tree)
        if self.healed_count > 0:
            ast.fix_missing_locations(healed_tree)
            return ast.unparse(healed_tree), self.healed_count
        return code, 0
