"""Regular Expression Denial of Service (ReDoS) AST Detector & Safe Regex Synthesizer.

Detects catastrophic backtracking regex patterns in Python source code (nested quantifiers,
overlapping repetitions, unbounded exponential permutations) passed to re.compile, re.search,
re.match, re.findall, re.sub, and automatically synthesizes safe linear regexes with bounded
quantification or defensive input guards.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple


# Common catastrophic backtracking signatures in regex literals:
# 1. Nested repetition: (a+)+, ([a-z]*)+, (\d+)*
# 2. Alternations with overlapping terms repeated: (a|a)+, (a|ab)+
# 3. Unbounded wildcards with repetition: (.*a)+
REDOS_NESTED_QUANTIFIERS = re.compile(r"\((?:[^()]|\([^()]*\))*[+*]\)[+*]")
REDOS_OVERLAPPING_ALT = re.compile(r"\(([a-zA-Z0-9_|]+)\)[+*]")
REDOS_UNBOUNDED_TOKEN = re.compile(r"\(\.\*[a-zA-Z0-9_-]+\)[+*]")


@dataclass
class ReDoSFinding:
    line_number: int
    call_name: str
    vulnerable_pattern: str
    vulnerability_reason: str
    recommended_pattern: str


class ReDoSVisitor(ast.NodeVisitor):
    """AST NodeVisitor that inspects regex invocations and pattern constants."""

    RE_METHODS = {"compile", "search", "match", "fullmatch", "findall", "finditer", "sub", "subn"}

    def __init__(self) -> None:
        self.findings: List[ReDoSFinding] = []

    def visit_Call(self, node: ast.Call) -> None:
        is_re_call = False
        method_name = ""

        # Check re.method(...)
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "re":
                if node.func.attr in self.RE_METHODS:
                    is_re_call = True
                    method_name = f"re.{node.func.attr}"
            elif node.func.attr in self.RE_METHODS:
                is_re_call = True
                method_name = node.func.attr
        elif isinstance(node.func, ast.Name) and node.func.id in self.RE_METHODS:
            is_re_call = True
            method_name = node.func.id

        if is_re_call and node.args:
            pattern_arg = node.args[0]
            if isinstance(pattern_arg, ast.Constant) and isinstance(pattern_arg.value, str):
                finding = self._analyze_regex_pattern(pattern_arg.value, node.lineno, method_name)
                if finding:
                    self.findings.append(finding)

        self.generic_visit(node)

    def _analyze_regex_pattern(self, pattern: str, lineno: int, call_name: str) -> Optional[ReDoSFinding]:
        # 1. Check for nested quantifiers: (x+)+, (x*)+, (x+)*
        if REDOS_NESTED_QUANTIFIERS.search(pattern):
            # Safe replacement: flatten nested quantifiers, e.g. (a+)+ -> a{1,256}
            safe_pat = re.sub(r"\(([a-zA-Z0-9_\-\.\s]+)[+*]\)[+*]", r"\1{1,256}", pattern)
            if safe_pat == pattern:
                safe_pat = re.sub(r"([+*])\)+[+*]", r"{1,256})", pattern)
            return ReDoSFinding(
                line_number=lineno,
                call_name=call_name,
                vulnerable_pattern=pattern,
                vulnerability_reason="Nested quantifier induces exponential catastrophic backtracking",
                recommended_pattern=safe_pat,
            )

        # 2. Check for unbounded repetition like (.*a)+
        if REDOS_UNBOUNDED_TOKEN.search(pattern):
            safe_pat = pattern.replace(".*", "[^\\n]{0,256}")
            return ReDoSFinding(
                line_number=lineno,
                call_name=call_name,
                vulnerable_pattern=pattern,
                vulnerability_reason="Unbounded wildcard repetition triggers polynomial or exponential ReDoS",
                recommended_pattern=safe_pat,
            )

        # 3. Check for overlapping alternation like (a|a)+ or (a|aa)+
        m = REDOS_OVERLAPPING_ALT.search(pattern)
        if m:
            parts = m.group(1).split("|")
            if len(parts) > 1 and len(set(parts)) < len(parts):
                # Duplicate alternation
                deduped = "|".join(dict.fromkeys(parts))
                safe_pat = pattern.replace(m.group(1), deduped)
                return ReDoSFinding(
                    line_number=lineno,
                    call_name=call_name,
                    vulnerable_pattern=pattern,
                    vulnerability_reason="Identical overlapping alternations in repeated group trigger ReDoS",
                    recommended_pattern=safe_pat,
                )

        return None


class ReDoSTransformer(ast.NodeTransformer):
    """AST NodeTransformer that patches vulnerable regex patterns into safe bounded equivalents."""

    def __init__(self, findings: List[ReDoSFinding]) -> None:
        self.findings_by_line = {f.line_number: f for f in findings}
        self.patch_count = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        finding = self.findings_by_line.get(node.lineno)
        if finding and node.args:
            pattern_arg = node.args[0]
            if isinstance(pattern_arg, ast.Constant) and pattern_arg.value == finding.vulnerable_pattern:
                node.args[0] = ast.Constant(value=finding.recommended_pattern)
                self.patch_count += 1
        return node


class ReDoSSynthesizer:
    """Orchestrator for ReDoS detection and AST pattern synthesis."""

    def analyze(self, source_code: str) -> List[ReDoSFinding]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return []
        visitor = ReDoSVisitor()
        visitor.visit(tree)
        return visitor.findings

    def synthesize(self, source_code: str) -> Tuple[str, List[ReDoSFinding]]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return source_code, []

        visitor = ReDoSVisitor()
        visitor.visit(tree)
        if not visitor.findings:
            return source_code, []

        transformer = ReDoSTransformer(visitor.findings)
        modified_tree = transformer.visit(tree)
        ast.fix_missing_locations(modified_tree)

        try:
            new_code = ast.unparse(modified_tree)
            compile(new_code, "<healed_redos>", "exec")
            return new_code, visitor.findings
        except Exception:
            return source_code, visitor.findings


def synthesize_redos_guards(source_code: str) -> Tuple[str, List[ReDoSFinding]]:
    engine = ReDoSSynthesizer()
    return engine.synthesize(source_code)
