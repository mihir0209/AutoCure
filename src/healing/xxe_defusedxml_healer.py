import ast
from typing import Tuple

class XxeDefusedxmlHealer(ast.NodeTransformer):
    def __init__(self):
        super().__init__()
        self.healed_count = 0

    def visit_Import(self, node: ast.Import) -> ast.AST:
        for alias in node.names:
            if alias.name == "xml.etree.ElementTree":
                self.healed_count += 1
                alias.name = "defusedxml.ElementTree"
        return node

    def heal_source(self, code: str) -> Tuple[str, int]:
        self.healed_count = 0
        tree = ast.parse(code)
        healed_tree = self.visit(tree)
        if self.healed_count > 0:
            ast.fix_missing_locations(healed_tree)
            return ast.unparse(healed_tree), self.healed_count
        return code, 0
