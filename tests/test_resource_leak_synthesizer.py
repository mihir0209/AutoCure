"""Tests for AutoCure Automated Resource Leak & Context Manager Synthesizer."""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from healing.resource_leak_synthesizer import (
    ResourceLeakSynthesizer,
    synthesize_resource_management,
)


def test_raw_open_transformed_to_with_context():
    raw_code = """
def read_app_config(file_path):
    f = open(file_path, "r")
    content = f.read()
    return content
"""
    new_code, findings = synthesize_resource_management(raw_code)
    assert len(findings) == 1
    assert findings[0].variable_name == "f"
    assert findings[0].remediation_kind == "WITH_CONTEXT_SYNTHESIS"
    assert "with open(file_path, 'r') as f:" in new_code


def test_synthesized_with_context_executes_and_closes_descriptor():
    raw_code = """
def process_data(file_path):
    f = open(file_path, "w")
    f.write("safe_data")
    return f
"""
    new_code, _ = synthesize_resource_management(raw_code)

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp:
        tmp_path = tmp.name

    local_ns = {}
    exec(new_code, local_ns)
    file_handle = local_ns["process_data"](tmp_path)

    # After exiting synthesized 'with' block, the file handle MUST be closed!
    assert file_handle.closed is True
    Path(tmp_path).unlink(missing_ok=True)


def test_clean_code_with_existing_context_manager_unmodified():
    clean_code = """
def safe_reader(path):
    with open(path) as f:
        return f.read()
"""
    new_code, findings = synthesize_resource_management(clean_code)
    assert len(findings) == 0
    assert "with open(path) as f:" in new_code
