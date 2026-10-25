"""Unit and Regression Tests for ReDoS AST Detector & Safe Regex Synthesizer."""

import pytest
from healing.redos_synthesizer import (
    ReDoSFinding,
    ReDoSSynthesizer,
    synthesize_redos_guards,
)


def test_redos_detects_nested_quantifiers():
    vulnerable_code = """
import re

def parse_input(data: str):
    pattern = re.compile(r"([a-z]+)+$")
    return pattern.match(data)
"""
    engine = ReDoSSynthesizer()
    findings = engine.analyze(vulnerable_code)
    assert len(findings) == 1
    assert "Nested quantifier" in findings[0].vulnerability_reason
    assert findings[0].line_number == 5


def test_redos_synthesizes_safe_pattern():
    vulnerable_code = """
import re

def search_text(text: str):
    return re.search(r"(a+)+", text)
"""
    healed, findings = synthesize_redos_guards(vulnerable_code)
    assert len(findings) == 1
    assert "(a+)+" not in healed
    assert "{1,256}" in healed
    # Verify healed code compiles and runs
    compiled = compile(healed, "<test>", "exec")
    namespace = {}
    exec(compiled, namespace)
    res = namespace["search_text"]("aaaa")
    assert res is not None


def test_redos_detects_duplicate_alternations():
    code = """
import re

regex = re.compile(r"(admin|admin)+")
"""
    engine = ReDoSSynthesizer()
    findings = engine.analyze(code)
    assert len(findings) == 1
    assert "overlapping" in findings[0].vulnerability_reason.lower()


def test_redos_preserves_safe_regex():
    safe_code = """
import re

pattern = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\\.[a-zA-Z0-9-.]+$")
m = re.match(r"\\d{4}-\\d{2}-\\d{2}", "2026-10-25")
"""
    healed, findings = synthesize_redos_guards(safe_code)
    assert len(findings) == 0
    assert healed.strip() == safe_code.strip()
