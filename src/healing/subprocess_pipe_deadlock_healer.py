import ast
from typing import Tuple

class SubprocessPipeDeadlockHealer(ast.NodeTransformer):
    def __init__(self):
        super().__init__()
        self.healed_count = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        # Matches proc.stdout.read() and rewrites to proc.communicate()[0]
        if isinstance(node.func, ast.Attribute) and node.func.attr == "read":
            if isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "stdout":
                proc_var = node.func.value.value
                self.healed_count += 1
                # Return proc_var.communicate()[0]
                comm_call = ast.Call(
                    func=ast.Attribute(value=proc_var, attr="communicate", ctx=ast.Load()),
                    args=[],
                    keywords=[]
                )
                return ast.Subscript(
                    value=comm_call,
                    slice=ast.Constant(value=0),
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
