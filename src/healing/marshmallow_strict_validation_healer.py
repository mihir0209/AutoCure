import ast
from typing import Tuple

class MarshmallowStrictValidationHealer(ast.NodeTransformer):
    def __init__(self):
        super().__init__()
        self.healed_count = 0

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        # Check if class inherits from Schema
        inherits_schema = any("Schema" in ast.unparse(b) for b in node.bases)
        if inherits_schema:
            has_meta = any(isinstance(stmt, ast.ClassDef) and stmt.name == "Meta" for stmt in node.body)
            if not has_meta:
                self.healed_count += 1
                # Inject class Meta: unknown = EXCLUDE
                meta_cls = ast.ClassDef(
                    name="Meta",
                    bases=[],
                    keywords=[],
                    body=[
                        ast.Assign(
                            targets=[ast.Name(id="unknown", ctx=ast.Store())],
                            value=ast.Name(id="EXCLUDE", ctx=ast.Load())
                        )
                    ],
                    decorator_list=[]
                )
                node.body.insert(0, meta_cls)
        return node

    def heal_source(self, code: str) -> Tuple[str, int]:
        self.healed_count = 0
        tree = ast.parse(code)
        healed_tree = self.visit(tree)
        if self.healed_count > 0:
            ast.fix_missing_locations(healed_tree)
            return ast.unparse(healed_tree), self.healed_count
        return code, 0
