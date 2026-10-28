import ast
from typing import Tuple

class XxeDefusalHealer(ast.NodeTransformer):
    def __init__(self):
        super().__init__()
        self.healed_count = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        func_name = ast.unparse(node.func)
        if "XMLParser" in func_name:
            has_resolve = any(kw.arg == "resolve_entities" for kw in node.keywords)
            if not has_resolve:
                self.healed_count += 1
                node.keywords.append(ast.keyword(arg="resolve_entities", value=ast.Constant(value=False)))
            has_network = any(kw.arg == "no_network" for kw in node.keywords)
            if not has_network:
                node.keywords.append(ast.keyword(arg="no_network", value=ast.Constant(value=True)))
        return node

    def heal_source(self, code: str) -> Tuple[str, int]:
        self.healed_count = 0
        tree = ast.parse(code)
        healed_tree = self.visit(tree)
        if self.healed_count > 0:
            ast.fix_missing_locations(healed_tree)
            return ast.unparse(healed_tree), self.healed_count
        return code, 0
