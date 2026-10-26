"""XML External Entity (XXE) AST Sanitizer & Defusedxml Synthesizer.

Detects vulnerable XML parsers from standard library `xml.etree.ElementTree`, `xml.dom.minidom`,
`xml.sax`, and `lxml.etree` vulnerable to billion laughs entity expansions, external DTD
retrieval, and local file disclosures. Synthesizes hardened replacements using `defusedxml`.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple


@dataclass
class XXEFinding:
    line_number: int
    vulnerable_parser: str
    vulnerability_reason: str
    remediation: str


class XXEVisitor(ast.NodeVisitor):
    """AST visitor that flags vulnerable standard XML parser calls."""

    VULNERABLE_MODULES = {"xml.etree.ElementTree", "xml.dom.minidom", "xml.sax", "lxml.etree"}
    VULNERABLE_FUNCS = {"parse", "fromstring", "parseString", "XML"}

    def __init__(self) -> None:
        self.findings: List[XXEFinding] = []

    def visit_Call(self, node: ast.Call) -> None:
        # Check ET.parse, ET.fromstring, minidom.parse, etc.
        if isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
            if func_name in self.VULNERABLE_FUNCS:
                # Check what value is: ET, xml.etree.ElementTree, minidom, etc.
                val_repr = ast.unparse(node.func.value)
                if val_repr in {"ET", "ElementTree", "xml.etree.ElementTree", "minidom", "xml.dom.minidom", "sax", "xml.sax", "lxml.etree", "etree"}:
                    self.findings.append(
                        XXEFinding(
                            line_number=node.lineno,
                            vulnerable_parser=f"{val_repr}.{func_name}",
                            vulnerability_reason="Standard XML parser is susceptible to XML External Entity (XXE) injection and Billion Laughs DoS",
                            remediation="Migrate parser to defusedxml equivalent",
                        )
                    )
        self.generic_visit(node)


class XXETransformer(ast.NodeTransformer):
    """AST transformer that migrates vulnerable XML parser imports and calls to defusedxml."""

    def __init__(self, findings: List[XXEFinding]) -> None:
        self.findings_by_line = {f.line_number: f for f in findings}
        self.patch_count = 0
        self.needs_defusedxml_import = False

    def visit_Import(self, node: ast.Import) -> ast.AST:
        # Check if importing xml.etree.ElementTree as ET
        new_names = []
        for alias in node.names:
            if alias.name == "xml.etree.ElementTree":
                new_names.append(ast.alias(name="defusedxml.ElementTree", asname=alias.asname or "ET"))
                self.patch_count += 1
            elif alias.name == "xml.dom.minidom":
                new_names.append(ast.alias(name="defusedxml.minidom", asname=alias.asname or "minidom"))
                self.patch_count += 1
            elif alias.name == "xml.sax":
                new_names.append(ast.alias(name="defusedxml.sax", asname=alias.asname or "sax"))
                self.patch_count += 1
            elif alias.name == "lxml.etree":
                new_names.append(ast.alias(name="defusedxml.lxml", asname=alias.asname or "etree"))
                self.patch_count += 1
            else:
                new_names.append(alias)
        node.names = new_names
        return node

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.AST:
        if node.module == "xml.etree.ElementTree":
            node.module = "defusedxml.ElementTree"
            self.patch_count += 1
        elif node.module == "xml.dom.minidom":
            node.module = "defusedxml.minidom"
            self.patch_count += 1
        elif node.module == "xml.sax":
            node.module = "defusedxml.sax"
            self.patch_count += 1
        elif node.module == "lxml.etree":
            node.module = "defusedxml.lxml"
            self.patch_count += 1
        return node


class XXESanitizer:
    """Orchestrates detection and remediation of XXE vulnerabilities."""

    def analyze(self, source_code: str) -> List[XXEFinding]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return []
        visitor = XXEVisitor()
        visitor.visit(tree)
        return visitor.findings

    def synthesize(self, source_code: str) -> Tuple[str, List[XXEFinding]]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return source_code, []

        visitor = XXEVisitor()
        visitor.visit(tree)
        if not visitor.findings:
            return source_code, []

        transformer = XXETransformer(visitor.findings)
        modified_tree = transformer.visit(tree)
        ast.fix_missing_locations(modified_tree)

        try:
            new_code = ast.unparse(modified_tree)
            compile(new_code, "<healed_xxe>", "exec")
            return new_code, visitor.findings
        except Exception:
            return source_code, visitor.findings


def sanitize_xxe(source_code: str) -> Tuple[str, List[XXEFinding]]:
    engine = XXESanitizer()
    return engine.synthesize(source_code)
