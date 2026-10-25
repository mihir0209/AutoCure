"""Tests for AutoCure Automated Null-Safety Guard Synthesizer."""

from __future__ import annotations

import pytest
from healing.null_safety_synthesizer import (
    NullSafetySynthesizer,
    synthesize_null_safety,
)


def test_attribute_dereference_guard_synthesis():
    # Code that would raise AttributeError: 'NoneType' object has no attribute 'profile'
    code = """
def get_user_status():
    user = None
    status = user.profile
    return status
"""
    new_code, findings = synthesize_null_safety(code)
    assert len(findings) == 1
    assert findings[0].variable_name == "user"
    assert findings[0].remediation_kind == "ATTRIBUTE_COALESCE"
    assert "user is not None" in new_code

    # Execute synthesized code safely: must return None without raising AttributeError
    local_ns = {}
    exec(new_code, local_ns)
    result = local_ns["get_user_status"]()
    assert result is None


def test_binary_operation_null_coalesce_synthesis():
    # Code that would raise TypeError: unsupported operand type(s) for +: 'int' and 'NoneType'
    code = """
def compute_salary(base):
    nullable_bonus = None
    total = base + nullable_bonus
    return total
"""
    new_code, findings = synthesize_null_safety(code)
    assert len(findings) == 1
    assert findings[0].variable_name == "nullable_bonus"
    assert findings[0].remediation_kind == "BINOP_COALESCE"

    # Execute synthesized code: 5000 + 0 = 5000
    local_ns = {}
    exec(new_code, local_ns)
    res = local_ns["compute_salary"](5000)
    assert res == 5000


def test_safe_code_remains_unmodified():
    clean_code = """
def safe_calculator(a: int, b: int) -> int:
    return a + b
"""
    new_code, findings = synthesize_null_safety(clean_code)
    assert len(findings) == 0
    assert "None" not in new_code


def test_explicit_nullable_parameter_annotation():
    code = """
def process_event(event):
    data = event.payload
    return data
"""
    new_code, findings = synthesize_null_safety(code, nullable_vars=["event"])
    assert len(findings) == 1
    assert findings[0].variable_name == "event"

    local_ns = {}
    exec(new_code, local_ns)
    # When passed None, returns None cleanly
    assert local_ns["process_event"](None) is None
