"""Unit & Adversarial Tests for Unhandled Exception Boundary Synthesizer."""

import ast
import json
import pytest
from healing.exception_boundary_synthesizer import (
    ExceptionBoundarySynthesizer,
    synthesize_exception_boundaries,
)


def test_synthesizes_json_loads_boundary():
    sample_code = """
def parse_payload(raw_text):
    data = json.loads(raw_text)
    return data
"""
    new_code, findings = synthesize_exception_boundaries(sample_code)

    assert len(findings) == 1
    assert findings[0].call_name == "json.loads"
    assert findings[0].exception_type == "json.JSONDecodeError"
    assert findings[0].suggested_fallback == "{}"

    assert "try:" in new_code
    assert "except json.JSONDecodeError:" in new_code
    assert "data = {}" in new_code

    # Execute synthesized code to verify it safely handles corrupt json
    scope = {"json": json}
    exec(new_code, scope)
    parse_fn = scope["parse_payload"]
    # Corrupted json returns fallback {} without crashing
    result = parse_fn("CORRUPTED_JSON_NOT_VALID")
    assert result == {}


def test_synthesizes_int_parsing_boundary():
    sample_code = """
def convert_age(age_str):
    age = int(age_str)
    return age + 1
"""
    new_code, findings = synthesize_exception_boundaries(sample_code)

    assert len(findings) == 1
    assert findings[0].call_name == "int"
    assert findings[0].exception_type == "ValueError"

    assert "try:" in new_code
    assert "except ValueError:" in new_code
    assert "age = 0" in new_code

    scope = {}
    exec(new_code, scope)
    convert_fn = scope["convert_age"]
    # Non-numeric string falls back to 0 -> returns 1
    assert convert_fn("not_a_number") == 1
    assert convert_fn("25") == 26


def test_ignores_already_protected_calls():
    sample_code = """
def safe_parse(payload):
    try:
        data = json.loads(payload)
    except Exception as e:
        data = {"fallback": True}
    return data
"""
    new_code, findings = synthesize_exception_boundaries(sample_code)

    # Already protected by try block, no new boundaries synthesized
    assert len(findings) == 0
    # AST structures should be equivalent
    assert ast.dump(ast.parse(new_code)) == ast.dump(ast.parse(sample_code))


def test_custom_rule_synthesis():
    custom_rules = {
        "fetch_config": ("ConnectionError", "{mode: offline}"),
    }
    sample_code = """
def load_app_config():
    cfg = fetch_config()
    return cfg
"""
    new_code, findings = synthesize_exception_boundaries(sample_code, custom_rules=custom_rules)

    assert len(findings) == 1
    assert findings[0].call_name == "fetch_config"
    assert "except ConnectionError:" in new_code
    assert "cfg = {mode: offline}" in new_code
