"""
AutoCure Timing Attack Constant-Time Compare AST Healer.
Transforms secret == token into hmac.compare_digest(secret, token).
"""
import ast
from typing import Tuple

class ConstantTimeCompareHealer(ast.NodeTransformer):
    def __init__(self):
        super().__init__()
        self.healed_count = 0

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)
        SECRET_NAMES = {"api_key", "secret", "token", "password", "hash", "signature"}
        if len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq):
            left_name = getattr(node.left, "id", "").lower()
            right_name = getattr(node.comparators[0], "id", "").lower() if node.comparators else ""
            if any(s in left_name or s in right_name for s in SECRET_NAMES):
                self.healed_count += 1
                return ast.Call(
                    func=ast.Attribute(value=ast.Name(id="hmac", ctx=ast.Load()), attr="compare_digest", ctx=ast.Load()),
                    args=[node.left, node.comparators[0]],
                    keywords=[],
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
