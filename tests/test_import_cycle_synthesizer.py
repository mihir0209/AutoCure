"""Tests for Circular Dependency & Module Import Cycle Break Synthesizer."""

import ast
import pytest
from healing.import_cycle_synthesizer import (
    ImportCycleSynthesizer,
    synthesize_import_cycle_break,
)


def test_type_checking_guard_synthesis_for_type_only_import():
    code = """
from app.models import UserProfile

def format_user_badge(profile: UserProfile) -> str:
    return "Badge: Active"
"""
    healed, findings = synthesize_import_cycle_break(
        code, cycle_module="app.models", cycle_symbol="UserProfile"
    )
    assert len(findings) == 1
    assert findings[0].resolution_strategy == "type_checking_guard"
    assert "from typing import TYPE_CHECKING" in healed
    assert "if TYPE_CHECKING:" in healed
    assert "from app.models import UserProfile" in healed


def test_lazy_local_import_synthesis_for_function_runtime_usage():
    code = """
from app.services import PaymentGateway

def process_checkout(cart_id: str):
    gateway = PaymentGateway()
    return gateway.charge(cart_id)
"""
    healed, findings = synthesize_import_cycle_break(
        code, cycle_module="app.services", cycle_symbol="PaymentGateway"
    )
    assert len(findings) == 1
    assert findings[0].resolution_strategy == "lazy_local_import"
    assert findings[0].target_function == "process_checkout"

    # Top level should no longer have the import
    lines = healed.strip().split("\n")
    assert not lines[0].startswith("from app.services")

    # Function body should contain the lazy import
    assert "def process_checkout(cart_id: str):" in healed
    assert "    from app.services import PaymentGateway" in healed
