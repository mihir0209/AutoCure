"""Unit and Regression Tests for Insecure Deserialization AST Sanitizer."""

import json
import pytest
from healing.deserialization_sanitizer import (
    DeserializationFinding,
    DeserializationSanitizer,
    sanitize_deserialization,
)


def test_deserialization_detects_unsafe_pickle_loads():
    code = """
import pickle

def load_session(data):
    return pickle.loads(data)
"""
    engine = DeserializationSanitizer()
    findings = engine.analyze(code)
    assert len(findings) == 1
    assert findings[0].library == "pickle"
    assert "RCE" in findings[0].vulnerability_reason


def test_deserialization_synthesizes_safe_yaml():
    code = """
import yaml

def load_config(raw_yaml):
    return yaml.load(raw_yaml, Loader=yaml.Loader)
"""
    healed, findings = sanitize_deserialization(code)
    assert len(findings) == 1
    assert "yaml.safe_load(raw_yaml)" in healed


def test_deserialization_preserves_safe_yaml():
    code = """
import yaml

def load_config(raw_yaml):
    return yaml.safe_load(raw_yaml)
"""
    healed, findings = sanitize_deserialization(code)
    assert len(findings) == 0
    assert healed.strip() == code.strip()
