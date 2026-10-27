"""
Subprocess Shell Injection & Argument Sanitizer AST Healer.

Scans Python AST for dangerous subprocess invocations (e.g., shell=True with dynamic arguments,
or legacy os.system/os.popen) and transforms them into secure, tokenized argument lists
using shlex.split with shell=False.
"""

import ast
from typing import Tuple, List, Optional


class ShellInjectionHealer(ast.NodeTransformer):
    """
    AST transformer that eliminates shell injection vulnerabilities by neutralizing
    shell=True and replacing unsafe os.system invocations with secure subprocess.run(shlex.split(...)).
    """

    SUBPROCESS_CALLS = {"run", "Popen", "call", "check_output", "check_call"}

    def __init__(self):
        super().__init__()
        self.healed_count = 0
        self.healed_locations: List[int] = []
        self.needs_shlex_import = False
        self.needs_subprocess_import = False

    def visit_Call(self, node: ast.Call) -> ast.AST:
        # First visit child nodes
        self.generic_visit(node)

        # 1. Detect os.system(cmd) or os.popen(cmd)
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            if node.func.value.id == "os" and node.func.attr in ("system", "popen"):
                if node.args:
                    self.healed_count += 1
                    self.healed_locations.append(node.lineno if hasattr(node, "lineno") else 0)
                    self.needs_shlex_import = True
                    self.needs_subprocess_import = True

                    # Transform to: subprocess.run(shlex.split(cmd), check=True)
                    cmd_arg = node.args[0]
                    shlex_call = ast.Call(
                        func=ast.Attribute(value=ast.Name(id="shlex", ctx=ast.Load()), attr="split", ctx=ast.Load()),
                        args=[cmd_arg],
                        keywords=[],
                    )
                    return ast.Call(
                        func=ast.Attribute(
                            value=ast.Name(id="subprocess", ctx=ast.Load()),
                            attr="run",
                            ctx=ast.Load(),
                        ),
                        args=[shlex_call],
                        keywords=[
                            ast.keyword(arg="shell", value=ast.Constant(value=False)),
                            ast.keyword(arg="check", value=ast.Constant(value=True)),
                        ],
                    )

        # 2. Detect subprocess.*(..., shell=True)
        is_subprocess = False
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            if node.func.value.id == "subprocess" and node.func.attr in self.SUBPROCESS_CALLS:
                is_subprocess = True
        elif isinstance(node.func, ast.Name) and node.func.id in self.SUBPROCESS_CALLS:
            is_subprocess = True

        if is_subprocess:
            # Check keywords for shell=True
            shell_kw = None
            for kw in node.keywords:
                if kw.arg == "shell":
                    shell_kw = kw
                    break

            if shell_kw and isinstance(shell_kw.value, ast.Constant) and shell_kw.value.value is True:
                self.healed_count += 1
                self.healed_locations.append(node.lineno if hasattr(node, "lineno") else 0)
                self.needs_shlex_import = True

                # Replace shell=True with shell=False
                shell_kw.value = ast.Constant(value=False)

                # If first arg is a single dynamic string or variable, wrap with shlex.split
                if node.args:
                    arg0 = node.args[0]
                    # If it's already a list, no need to shlex.split
                    if not isinstance(arg0, (ast.List, ast.Tuple)):
                        node.args[0] = ast.Call(
                            func=ast.Attribute(
                                value=ast.Name(id="shlex", ctx=ast.Load()),
                                attr="split",
                                ctx=ast.Load(),
                            ),
                            args=[arg0],
                            keywords=[],
                        )

        return node

    def heal_source(self, source_code: str) -> Tuple[str, int]:
        """
        Parses source code, applies shell injection sanitization, injects imports if missing,
        and returns the healed source code and total count of remediated locations.
        """
        self.healed_count = 0
        self.healed_locations = []
        self.needs_shlex_import = False
        self.needs_subprocess_import = False

        tree = ast.parse(source_code)
        healed_tree = self.visit(tree)

        if self.healed_count == 0:
            return source_code, 0

        # Inject necessary imports at module top if not already present
        existing_imports = set()
        for stmt in tree.body:
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    existing_imports.add(alias.name)

        new_imports = []
        if self.needs_shlex_import and "shlex" not in existing_imports:
            new_imports.append(ast.Import(names=[ast.alias(name="shlex")]))
        if self.needs_subprocess_import and "subprocess" not in existing_imports:
            new_imports.append(ast.Import(names=[ast.alias(name="subprocess")]))

        if new_imports:
            healed_tree.body = new_imports + healed_tree.body

        ast.fix_missing_locations(healed_tree)
        healed_source = ast.unparse(healed_tree)
        return healed_source, self.healed_count
