"""Unit & Adversarial Tests for Automated Invariant Guard Synthesizer."""

import math
import pytest
from healing.invariant_guard_synthesizer import (
    InvariantGuardSynthesizer,
    synthesize_invariant_guards,
)


def test_synthesizes_zero_division_guard():
    source = """
def calc_average(total, count):
    avg = total / count
    return avg
"""
    new_code, findings = synthesize_invariant_guards(source)

    assert len(findings) == 1
    assert findings[0].invariant_type == "ZERO_DIVISION_GUARD"
    assert "count if count != 0 else 1.0" in new_code

    # Execute with zero count to verify ZeroDivisionError is avoided
    scope = {}
    exec(new_code, scope)
    calc_fn = scope["calc_average"]
    res = calc_fn(100, 0)
    assert res == 100.0  # 100 / 1.0 fallback


def test_preserves_safe_constant_division():
    source = """
def halve(x):
    return x / 2
"""
    new_code, findings = synthesize_invariant_guards(source)

    assert len(findings) == 0
    assert "x / 2" in new_code


def test_synthesizes_negative_sqrt_clamp():
    source = """
def compute_hypot(delta):
    return math.sqrt(delta)
"""
    new_code, findings = synthesize_invariant_guards(source)

    assert len(findings) == 1
    assert findings[0].invariant_type == "NEGATIVE_SQRT_GUARD"
    assert "math.sqrt(max(0.0, delta))" in new_code

    scope = {"math": math}
    exec(new_code, scope)
    sqrt_fn = scope["compute_hypot"]
    # Negative delta clamped to 0.0 -> returns 0.0 without ValueError
    assert sqrt_fn(-100.0) == 0.0
    assert sqrt_fn(16.0) == 4.0
