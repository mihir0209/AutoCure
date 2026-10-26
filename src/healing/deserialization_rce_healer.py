import ast
from typing import Tuple, List

class DeserializationRceHealer(ast.NodeTransformer):
    """
    Detects unsafe object deserialization calls that enable Remote Code Execution
    via pickle.loads, pickle.load, yaml.load without SafeLoader, and rewrites
    them into safe deserializers (json.loads or yaml.safe_load).
    """

    def __init__(self):
        super().__init__()
        self.healed_count = 0
        self.findings: List[str] = []

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)

        # 1. Detect pickle.loads(data) -> json.loads(data)
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "pickle":
                if node.func.attr in ("loads", "load"):
                    self.healed_count += 1
                    self.findings.append(f"Replaced unsafe pickle.{node.func.attr} with json.loads to prevent RCE gadget chain")
                    new_func = ast.Attribute(
                        value=ast.Name(id="json", ctx=ast.Load()),
                        attr="loads",
                        ctx=ast.Load()
                    )
                    return ast.copy_location(ast.Call(func=new_func, args=node.args, keywords=[]), node)

            # 2. Detect yaml.load(stream) without SafeLoader -> yaml.safe_load(stream)
            elif isinstance(node.func.value, ast.Name) and node.func.value.id == "yaml":
                if node.func.attr == "load":
                    has_safe_loader = any(
                        kw.arg == "Loader" and isinstance(kw.value, ast.Attribute) and kw.value.attr in ("SafeLoader", "CSafeLoader")
                        for kw in node.keywords
                    )
                    if not has_safe_loader:
                        self.healed_count += 1
                        self.findings.append("Rewrote unsafe yaml.load to yaml.safe_load")
                        new_func = ast.Attribute(
                            value=ast.Name(id="yaml", ctx=ast.Load()),
                            attr="safe_load",
                            ctx=ast.Load()
                        )
                        return ast.copy_location(ast.Call(func=new_func, args=node.args[:1], keywords=[]), node)

        return node

def heal_deserialization_vulnerabilities(source_code: str) -> Tuple[str, int, List[str]]:
    tree = ast.parse(source_code)
    healer = DeserializationRceHealer()
    healed_tree = healer.visit(tree)
    ast.fix_missing_locations(healed_tree)
    return ast.unparse(healed_tree), healer.healed_count, healer.findings
