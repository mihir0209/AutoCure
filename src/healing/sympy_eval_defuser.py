import ast
from typing import Tuple

class SympyEvalDefuser(ast.NodeTransformer):
    def __init__(self):
        super().__init__()
        self.healed_count = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        func_name = ast.unparse(node.func)
        if "sympify" in func_name:
            # Check if evaluate keyword is set to True or missing
            has_eval_kw = False
            for kw in node.keywords:
                if kw.arg == "evaluate":
                    has_eval_kw = True
                    if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        self.healed_count += 1
                        kw.value = ast.Constant(value=False)
            if not has_eval_kw:
                self.healed_count += 1
                node.keywords.append(ast.keyword(arg="evaluate", value=ast.Constant(value=False)))
        return node

    def heal_source(self, code: str) -> Tuple[str, int]:
        self.healed_count = 0
        tree = ast.parse(code)
        healed_tree = self.visit(tree)
        if self.healed_count > 0:
            ast.fix_missing_locations(healed_tree)
            return ast.unparse(healed_tree), self.healed_count
        return code, 0
