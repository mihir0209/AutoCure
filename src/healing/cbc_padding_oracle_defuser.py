import ast
from typing import Tuple

class CbcPaddingOracleDefuser(ast.NodeTransformer):
    def __init__(self):
        super().__init__()
        self.healed_count = 0

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        self.generic_visit(node)
        # Migrate AES.MODE_CBC to AES.MODE_GCM to eliminate padding oracle vulnerabilities (e.g. POODLE, Lucky13)
        if node.attr == "MODE_CBC":
            self.healed_count += 1
            node.attr = "MODE_GCM"
        return node

    def heal_source(self, code: str) -> Tuple[str, int]:
        self.healed_count = 0
        tree = ast.parse(code)
        healed_tree = self.visit(tree)
        if self.healed_count > 0:
            ast.fix_missing_locations(healed_tree)
            return ast.unparse(healed_tree), self.healed_count
        return code, 0
