import ast
from typing import Tuple

class NamedTempfileDeleteHealer(ast.NodeTransformer):
    def __init__(self):
        super().__init__()
        self.healed_count = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        func_name = ast.unparse(node.func)
        if "NamedTemporaryFile" in func_name:
            # Check delete keyword: delete=False leads to disk leaks on Windows/Linux if not cleaned
            has_delete = False
            for kw in node.keywords:
                if kw.arg == "delete":
                    has_delete = True
                    if isinstance(kw.value, ast.Constant) and kw.value.value is False:
                        self.healed_count += 1
                        kw.value = ast.Constant(value=True)
            if not has_delete:
                self.healed_count += 1
                node.keywords.append(ast.keyword(arg="delete", value=ast.Constant(value=True)))
        return node

    def heal_source(self, code: str) -> Tuple[str, int]:
        self.healed_count = 0
        tree = ast.parse(code)
        healed_tree = self.visit(tree)
        if self.healed_count > 0:
            ast.fix_missing_locations(healed_tree)
            return ast.unparse(healed_tree), self.healed_count
        return code, 0
