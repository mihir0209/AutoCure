import ast
from typing import Tuple

class AssertStatementProductionHealer(ast.NodeTransformer):
    def __init__(self):
        super().__init__()
        self.healed_count = 0

    def visit_Assert(self, node: ast.Assert) -> ast.AST:
        self.healed_count += 1
        # Convert: assert test, msg -> if not (test): raise AssertionError(msg)
        not_test = ast.UnaryOp(op=ast.Not(), operand=node.test)
        msg_expr = node.msg if node.msg is not None else ast.Constant(value="Assertion condition failed")
        raise_stmt = ast.Raise(
            exc=ast.Call(
                func=ast.Name(id="AssertionError", ctx=ast.Load()),
                args=[msg_expr],
                keywords=[]
            ),
            cause=None
        )
        return ast.If(test=not_test, body=[raise_stmt], orelse=[])

    def heal_source(self, code: str) -> Tuple[str, int]:
        self.healed_count = 0
        tree = ast.parse(code)
        healed_tree = self.visit(tree)
        if self.healed_count > 0:
            ast.fix_missing_locations(healed_tree)
            return ast.unparse(healed_tree), self.healed_count
        return code, 0
