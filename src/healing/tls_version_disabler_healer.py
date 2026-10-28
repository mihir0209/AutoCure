import ast
from typing import Tuple

class TlsVersionDisablerHealer(ast.NodeTransformer):
    INSECURE_VERSIONS = {"PROTOCOL_SSLv23", "PROTOCOL_SSLv2", "PROTOCOL_SSLv3", "PROTOCOL_TLSv1", "PROTOCOL_TLSv1_1"}

    def __init__(self):
        super().__init__()
        self.healed_count = 0

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        self.generic_visit(node)
        if node.attr in self.INSECURE_VERSIONS:
            self.healed_count += 1
            node.attr = "PROTOCOL_TLS_CLIENT"
        return node

    def heal_source(self, code: str) -> Tuple[str, int]:
        self.healed_count = 0
        tree = ast.parse(code)
        healed_tree = self.visit(tree)
        if self.healed_count > 0:
            ast.fix_missing_locations(healed_tree)
            return ast.unparse(healed_tree), self.healed_count
        return code, 0
