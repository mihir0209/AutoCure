"""
AutoCure Insecure YAML & Deserialization AST Healer.
Transforms unsafe yaml.load(f) into yaml.safe_load(f).
"""
import ast
from typing import Tuple, List

class YamlSafeLoadHealer(ast.NodeTransformer):
    def __init__(self):
        super().__init__()
        self.healed_count = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "load":
            if isinstance(node.func.value, ast.Name) and node.func.value.id in ("yaml", "pyyaml"):
                # If Loader keyword is absent, rewrite to safe_load
                has_loader = any(kw.arg == "Loader" for kw in node.keywords)
                if not has_loader:
                    self.healed_count += 1
                    node.func.attr = "safe_load"
        return node

    def heal_source(self, code: str) -> Tuple[str, int]:
        self.healed_count = 0
        tree = ast.parse(code)
        healed_tree = self.visit(tree)
        if self.healed_count > 0:
            ast.fix_missing_locations(healed_tree)
            return ast.unparse(healed_tree), self.healed_count
        return code, 0
