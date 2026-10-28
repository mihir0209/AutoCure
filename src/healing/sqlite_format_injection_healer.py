import ast
from typing import Tuple

class SqliteFormatInjectionHealer(ast.NodeTransformer):
    def __init__(self):
        super().__init__()
        self.healed_count = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        func_name = ast.unparse(node.func)
        if "execute" in func_name and node.args:
            sql_arg = node.args[0]
            # If query is f-string or % formatting e.g. f"SELECT * FROM users WHERE id = '{uid}'"
            if isinstance(sql_arg, ast.JoinedStr):
                self.healed_count += 1
                # Replace with parameterized query using '?'
                text_parts = []
                param_vars = []
                for val in sql_arg.values:
                    if isinstance(val, ast.Constant):
                        text_parts.append(val.value.replace("'", ""))
                    elif isinstance(val, ast.FormattedValue):
                        text_parts.append("?")
                        param_vars.append(val.value)
                new_sql = "".join(text_parts)
                node.args[0] = ast.Constant(value=new_sql)
                if len(node.args) == 1:
                    node.args.append(ast.Tuple(elts=param_vars, ctx=ast.Load()))
        return node

    def heal_source(self, code: str) -> Tuple[str, int]:
        self.healed_count = 0
        tree = ast.parse(code)
        healed_tree = self.visit(tree)
        if self.healed_count > 0:
            ast.fix_missing_locations(healed_tree)
            return ast.unparse(healed_tree), self.healed_count
        return code, 0
