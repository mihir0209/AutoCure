import ast
from typing import Tuple

class ThreadpoolShutdownLeakHealer(ast.NodeTransformer):
    def __init__(self):
        super().__init__()
        self.healed_count = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        func_name = ast.unparse(node.func)
        if func_name.endswith(".shutdown") and "executor" in func_name:
            # Ensure wait=True and cancel_futures=True are explicitly passed to prevent hanging worker threads
            has_cancel = any(kw.arg == "cancel_futures" for kw in node.keywords)
            if not has_cancel:
                self.healed_count += 1
                node.keywords.append(ast.keyword(arg="wait", value=ast.Constant(value=True)))
                node.keywords.append(ast.keyword(arg="cancel_futures", value=ast.Constant(value=True)))
        return node

    def heal_source(self, code: str) -> Tuple[str, int]:
        self.healed_count = 0
        tree = ast.parse(code)
        healed_tree = self.visit(tree)
        if self.healed_count > 0:
            ast.fix_missing_locations(healed_tree)
            return ast.unparse(healed_tree), self.healed_count
        return code, 0
