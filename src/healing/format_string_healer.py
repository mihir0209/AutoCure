"""
Format String Injection & Attribute Traversal AST Healer.

Scans Python AST for dangerous format string patterns (str.format() or format_map() with
untrusted attribute/item traversal) that expose private object internals and credentials,
and synthesizes secure sanitization wrappers or string interpolation guardrails.
"""

import ast
from typing import Tuple, List, Any


class FormatStringHealer(ast.NodeTransformer):
    """
    Transforms vulnerable str.format() and format_map() invocations to safe string formatting
    by injecting attribute-access sanitization or converting vulnerable expressions.
    """

    DANGEROUS_TRAVERSAL_ATTRS = {"__class__", "__globals__", "__init__", "__mro__", "__subclasses__", "__dict__"}

    def __init__(self):
        super().__init__()
        self.healed_count = 0
        self.healed_locations: List[int] = []

    def is_vulnerable_format_call(self, node: ast.Call) -> bool:
        """
        Detects calls where .format(...) or .format_map(...) is invoked on an attribute
        or dynamically constructed string expression.
        """
        if not isinstance(node.func, ast.Attribute):
            return False

        if node.func.attr not in ("format", "format_map"):
            return False

        # 1. Check if format string is a literal with dangerous attribute accesses like {0.__class__}
        if isinstance(node.func.value, ast.Constant) and isinstance(node.func.value.value, str):
            val = node.func.value.value
            for dangerous in self.DANGEROUS_TRAVERSAL_ATTRS:
                if dangerous in val:
                    return True

        # 2. Check if format string is an arbitrary variable (dynamic user template)
        if isinstance(node.func.value, (ast.Name, ast.Call, ast.Subscript)):
            return True

        return False

    def heal_source(self, source_code: str) -> Tuple[str, int]:
        """Parses source code, heals vulnerable format string calls, and returns healed code + count."""
        tree = ast.parse(source_code)
        healed_tree = self.visit(tree)
        ast.fix_missing_locations(healed_tree)
        healed_source = ast.unparse(healed_tree)
        return healed_source, self.healed_count

    def visit_Call(self, node: ast.Call) -> Any:
        self.generic_visit(node)
        if self.is_vulnerable_format_call(node):
            self.healed_count += 1
            lineno = getattr(node, "lineno", 0)
            self.healed_locations.append(lineno)

            # Transform:
            # If literal with dangerous attributes: sanitize the string constant
            if isinstance(node.func.value, ast.Constant) and isinstance(node.func.value.value, str):
                cleaned_str = node.func.value.value
                for dangerous in self.DANGEROUS_TRAVERSAL_ATTRS:
                    cleaned_str = cleaned_str.replace(dangerous, "_safe_sanitized")
                node.func.value = ast.Constant(value=cleaned_str)
                return node

            # If dynamic template: wrap in safe template stripping:
            # re.sub(r__w+__, _sanitized, template).format(...)
            safe_wrapper_call = ast.Call(
                func=ast.Attribute(
                    value=ast.Call(
                        func=ast.Attribute(
                            value=ast.Name(id="_autocure_sanitize_fmt", ctx=ast.Load()),
                            attr="strip_dunder",
                            ctx=ast.Load(),
                        ),
                        args=[node.func.value],
                        keywords=[],
                    ),
                    attr=node.func.attr,
                    ctx=ast.Load(),
                ),
                args=node.args,
                keywords=node.keywords,
            )
            return safe_wrapper_call

        return node
