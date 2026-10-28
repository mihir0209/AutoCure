import ast
from typing import Tuple

class StaticCryptoSaltHealer(ast.NodeTransformer):
    def __init__(self):
        super().__init__()
        self.healed_count = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        func_name = ast.unparse(node.func)
        # Check AES cipher init or PBKDF2 with static byte string IV/salt
        if any(c in func_name for c in ("Cipher", "AES.new", "pbkdf2_hmac")):
            for idx, arg in enumerate(node.args):
                # If an argument is a literal constant byte-string of length 16 or 32
                if isinstance(arg, ast.Constant) and isinstance(arg.value, bytes) and len(arg.value) in (16, 32):
                    self.healed_count += 1
                    # Replace with os.urandom(16)
                    node.args[idx] = ast.Call(
                        func=ast.Attribute(value=ast.Name(id="os", ctx=ast.Load()), attr="urandom", ctx=ast.Load()),
                        args=[ast.Constant(value=len(arg.value))],
                        keywords=[]
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
