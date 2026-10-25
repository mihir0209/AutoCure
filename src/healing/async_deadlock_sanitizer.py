"""Async/Await Concurrency Deadlock & Blocking Call Sanitizer.

Detects event-loop blocking synchronous I/O and sleep calls inside async def coroutines
and automatically rewrites them to non-blocking asyncio equivalents or to_thread dispatches.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple


@dataclass
class AsyncDeadlockFinding:
    coroutine_name: str
    call_name: str
    line_number: int
    remediation_applied: str


class AsyncDeadlockSanitizer(ast.NodeTransformer):
    """Scans and transforms blocking synchronous calls within async coroutines."""

    def __init__(self, known_async_funcs: Optional[Set[str]] = None) -> None:
        super().__init__()
        self.known_async_funcs: Set[str] = known_async_funcs or set()
        self.findings: List[AsyncDeadlockFinding] = []
        self._in_async_def = False
        self._current_async_fn: Optional[str] = None
        self._requires_asyncio_import = False

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        old_state = self._in_async_def
        old_fn = self._current_async_fn

        self._in_async_def = True
        self._current_async_fn = node.name
        self.generic_visit(node)

        self._in_async_def = old_state
        self._current_async_fn = old_fn
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        # Regular synchronous functions should NOT be altered
        old_state = self._in_async_def
        self._in_async_def = False
        self.generic_visit(node)
        self._in_async_def = old_state
        return node

    def visit_Expr(self, node: ast.Expr) -> ast.AST:
        if not self._in_async_def or not isinstance(node.value, ast.Call):
            return self.generic_visit(node)

        call_str = ast.unparse(node.value.func)

        # 1. time.sleep(n) -> await asyncio.sleep(n)
        if call_str in ("time.sleep", "sleep"):
            self._requires_asyncio_import = True
            new_call = ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="asyncio", ctx=ast.Load()),
                    attr="sleep",
                    ctx=ast.Load(),
                ),
                args=node.value.args,
                keywords=node.value.keywords,
            )
            await_node = ast.Await(value=new_call)
            ast.copy_location(await_node, node.value)
            self.findings.append(
                AsyncDeadlockFinding(
                    coroutine_name=self._current_async_fn or "unknown",
                    call_name=call_str,
                    line_number=node.lineno,
                    remediation_applied="Transformed blocking time.sleep to await asyncio.sleep",
                )
            )
            node.value = await_node
            return node

        # 2. Known async function called without await -> await func(...)
        if call_str in self.known_async_funcs:
            await_node = ast.Await(value=node.value)
            ast.copy_location(await_node, node.value)
            self.findings.append(
                AsyncDeadlockFinding(
                    coroutine_name=self._current_async_fn or "unknown",
                    call_name=call_str,
                    line_number=node.lineno,
                    remediation_applied="Inserted missing await expression for coroutine call",
                )
            )
            node.value = await_node
            return node

        # 3. Synchronous blocking I/O calls (e.g. requests.get, urllib) -> await asyncio.to_thread(func, *args)
        if call_str in ("requests.get", "requests.post", "urllib.request.urlopen"):
            self._requires_asyncio_import = True
            to_thread_call = ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="asyncio", ctx=ast.Load()),
                    attr="to_thread",
                    ctx=ast.Load(),
                ),
                args=[node.value.func] + node.value.args,
                keywords=node.value.keywords,
            )
            await_node = ast.Await(value=to_thread_call)
            ast.copy_location(await_node, node.value)
            self.findings.append(
                AsyncDeadlockFinding(
                    coroutine_name=self._current_async_fn or "unknown",
                    call_name=call_str,
                    line_number=node.lineno,
                    remediation_applied=f"Wrapped blocking {call_str} in await asyncio.to_thread",
                )
            )
            node.value = await_node
            return node

        return self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        if not self._in_async_def or not isinstance(node.value, ast.Call):
            return self.generic_visit(node)

        call_str = ast.unparse(node.value.func)

        # e.g. resp = requests.get(url) inside async def -> resp = await asyncio.to_thread(requests.get, url)
        if call_str in ("requests.get", "requests.post", "urllib.request.urlopen"):
            self._requires_asyncio_import = True
            to_thread_call = ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="asyncio", ctx=ast.Load()),
                    attr="to_thread",
                    ctx=ast.Load(),
                ),
                args=[node.value.func] + node.value.args,
                keywords=node.value.keywords,
            )
            await_node = ast.Await(value=to_thread_call)
            ast.copy_location(await_node, node.value)
            self.findings.append(
                AsyncDeadlockFinding(
                    coroutine_name=self._current_async_fn or "unknown",
                    call_name=call_str,
                    line_number=node.lineno,
                    remediation_applied=f"Wrapped blocking {call_str} in await asyncio.to_thread",
                )
            )
            node.value = await_node
            return node

        # Missing await on assignment: data = fetch_async()
        if call_str in self.known_async_funcs:
            await_node = ast.Await(value=node.value)
            ast.copy_location(await_node, node.value)
            self.findings.append(
                AsyncDeadlockFinding(
                    coroutine_name=self._current_async_fn or "unknown",
                    call_name=call_str,
                    line_number=node.lineno,
                    remediation_applied="Inserted missing await expression for assigned coroutine call",
                )
            )
            node.value = await_node
            return node

        return self.generic_visit(node)


def sanitize_async_deadlocks(
    source_code: str,
    known_async_funcs: Optional[Set[str]] = None,
) -> Tuple[str, List[AsyncDeadlockFinding]]:
    """Analyzes and sanitizes blocking synchronous patterns in coroutines."""
    tree = ast.parse(source_code)

    # First pass: collect async def names in module
    declared_async = set(known_async_funcs or set())
    for n in ast.walk(tree):
        if isinstance(n, ast.AsyncFunctionDef):
            declared_async.add(n.name)

    sanitizer = AsyncDeadlockSanitizer(declared_async)
    transformed = sanitizer.visit(tree)
    ast.fix_missing_locations(transformed)

    new_source = ast.unparse(transformed)
    if sanitizer._requires_asyncio_import and "import asyncio" not in new_source:
        new_source = "import asyncio\n" + new_source

    compile(new_source, "<sanitized_async>", mode="exec")
    return new_source, sanitizer.findings
