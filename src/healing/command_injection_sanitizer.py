"""Command Injection & Insecure Subprocess AST Sanitizer.

Detects dangerous shell executions such as subprocess calls with `shell=True`,
`os.system(...)`, and `os.popen(...)` that consume dynamic or concatenated command
strings. Synthesizes hardened, parameterized argument vectors via `shlex.split`
and safe `subprocess.run(..., shell=False)` invocations.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple


@dataclass
class CommandInjectionFinding:
    line_number: int
    vulnerable_call: str
    vulnerability_reason: str
    remediation: str


class CommandInjectionVisitor(ast.NodeVisitor):
    """AST visitor that flags unsafe shell commands and shell=True invocations."""

    DANGEROUS_SUBPROCESS_FUNCS = {"run", "Popen", "call", "check_call", "check_output"}
    DANGEROUS_OS_FUNCS = {"system", "popen"}

    def __init__(self) -> None:
        self.findings: List[CommandInjectionFinding] = []

    def visit_Call(self, node: ast.Call) -> None:
        # Check os.system(...) or os.popen(...)
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            module_name = node.func.value.id
            method_name = node.func.attr

            if module_name == "os" and method_name in self.DANGEROUS_OS_FUNCS:
                self.findings.append(
                    CommandInjectionFinding(
                        line_number=node.lineno,
                        vulnerable_call=f"os.{method_name}",
                        vulnerability_reason=f"Direct shell invocation via os.{method_name} allows arbitrary command injection",
                        remediation="subprocess.run with argv list and shell=False",
                    )
                )

            # Check subprocess.*(..., shell=True)
            elif module_name == "subprocess" and method_name in self.DANGEROUS_SUBPROCESS_FUNCS:
                for kw in node.keywords:
                    if kw.arg == "shell":
                        # Check if shell is True
                        if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            self.findings.append(
                                CommandInjectionFinding(
                                    line_number=node.lineno,
                                    vulnerable_call=f"subprocess.{method_name}(..., shell=True)",
                                    vulnerability_reason="Subprocess invocation with shell=True exposes shell expansion and command chaining",
                                    remediation="Set shell=False and pass command as tokenized argument list",
                                )
                            )
                        elif isinstance(kw.value, ast.NameConstant) and kw.value.value is True:
                            self.findings.append(
                                CommandInjectionFinding(
                                    line_number=node.lineno,
                                    vulnerable_call=f"subprocess.{method_name}(..., shell=True)",
                                    vulnerability_reason="Subprocess invocation with shell=True exposes shell expansion and command chaining",
                                    remediation="Set shell=False and pass command as tokenized argument list",
                                )
                            )

        self.generic_visit(node)


class CommandInjectionTransformer(ast.NodeTransformer):
    """AST transformer that removes shell=True and converts os.system into safe subprocess."""

    def __init__(self, findings: List[CommandInjectionFinding]) -> None:
        self.findings_by_line = {f.line_number: f for f in findings}
        self.patch_count = 0
        self.needs_shlex_import = False
        self.needs_subprocess_import = False

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        finding = self.findings_by_line.get(node.lineno)
        if not finding:
            return node

        # Case 1: subprocess.*(..., shell=True) -> change shell=False
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            if node.func.value.id == "subprocess" and node.func.attr in CommandInjectionVisitor.DANGEROUS_SUBPROCESS_FUNCS:
                # Replace or remove shell keyword
                new_keywords = []
                for kw in node.keywords:
                    if kw.arg == "shell":
                        # Replace value with False
                        new_keywords.append(ast.keyword(arg="shell", value=ast.Constant(value=False)))
                    else:
                        new_keywords.append(kw)
                node.keywords = new_keywords

                # If first arg is a formatted string or string concatenation or string var, wrap in shlex.split(arg) if not already a list
                if node.args and not isinstance(node.args[0], (ast.List, ast.Tuple)):
                    first_arg = node.args[0]
                    # Wrap: shlex.split(first_arg)
                    wrapped_arg = ast.Call(
                        func=ast.Attribute(
                            value=ast.Name(id="shlex", ctx=ast.Load()),
                            attr="split",
                            ctx=ast.Load(),
                        ),
                        args=[first_arg],
                        keywords=[],
                    )
                    node.args[0] = wrapped_arg
                    self.needs_shlex_import = True

                self.patch_count += 1
                return node

            # Case 2: os.system(cmd) -> subprocess.run(shlex.split(cmd), check=True)
            elif node.func.value.id == "os" and node.func.attr == "system":
                arg = node.args[0] if node.args else ast.Constant(value="")
                # Wrap with shlex.split
                split_arg = ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id="shlex", ctx=ast.Load()),
                        attr="split",
                        ctx=ast.Load(),
                    ),
                    args=[arg],
                    keywords=[],
                )
                replacement = ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id="subprocess", ctx=ast.Load()),
                        attr="run",
                        ctx=ast.Load(),
                    ),
                    args=[split_arg],
                    keywords=[
                        ast.keyword(arg="check", value=ast.Constant(value=True)),
                        ast.keyword(arg="shell", value=ast.Constant(value=False)),
                    ],
                )
                self.needs_shlex_import = True
                self.needs_subprocess_import = True
                self.patch_count += 1
                return replacement

        return node


class CommandInjectionSanitizer:
    """Orchestrates detection and remediation of command injection flaws."""

    def analyze(self, source_code: str) -> List[CommandInjectionFinding]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return []
        visitor = CommandInjectionVisitor()
        visitor.visit(tree)
        return visitor.findings

    def synthesize(self, source_code: str) -> Tuple[str, List[CommandInjectionFinding]]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return source_code, []

        visitor = CommandInjectionVisitor()
        visitor.visit(tree)
        if not visitor.findings:
            return source_code, []

        transformer = CommandInjectionTransformer(visitor.findings)
        modified_tree = transformer.visit(tree)

        # Inject necessary imports at module top if required
        existing_imports = set()
        for node in modified_tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    existing_imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                existing_imports.add(node.module)

        new_import_nodes = []
        if transformer.needs_shlex_import and "shlex" not in existing_imports:
            new_import_nodes.append(ast.Import(names=[ast.alias(name="shlex")]))
        if transformer.needs_subprocess_import and "subprocess" not in existing_imports:
            new_import_nodes.append(ast.Import(names=[ast.alias(name="subprocess")]))

        if new_import_nodes:
            modified_tree.body = new_import_nodes + modified_tree.body

        ast.fix_missing_locations(modified_tree)

        try:
            new_code = ast.unparse(modified_tree)
            compile(new_code, "<healed_command_injection>", "exec")
            return new_code, visitor.findings
        except Exception:
            return source_code, visitor.findings


def sanitize_command_injection(source_code: str) -> Tuple[str, List[CommandInjectionFinding]]:
    engine = CommandInjectionSanitizer()
    return engine.synthesize(source_code)
