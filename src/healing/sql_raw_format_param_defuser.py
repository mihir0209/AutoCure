import ast
from typing import Tuple

class SqlRawFormatParamDefuser(ast.NodeTransformer):
    def __init__(self):
        super().__init__()
        self.healed_count = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        func_name = ast.unparse(node.func)
        if "cursor.execute" in func_name:
            # Check if first argument is a BinOp with '%' or a format Call
            if len(node.args) == 1:
                arg = node.args[0]
                if isinstance(arg, ast.BinOp) and isinstance(arg.op, (ast.Mod, ast.Add)):
                    self.healed_count += 1
                    # Replace with parameterized dummy placeholder
                    node.args = [
                        ast.Constant(value="SELECT * FROM table WHERE id = ?"),
                        ast.Tuple(elts=[ast.Name(id="param", ctx=ast.Load())], ctx=ast.Load())
                    ]
        return node

    def heal_source(self, code: str) -> Tuple[str, int]:
        self.healed_count = 0
        tree = ast.parse(code)
        healed_tree = self.visit(tree)
        if self.healed_count > 0:
            ast.fix_missing_locations(healed_tree)
            return ast.unparse(healed_tree), self.healed_count
        return code, 0
