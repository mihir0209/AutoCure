import pytest
from healing.deserialization_sanitizer import (
    DeserializationSanitizer,
    sanitize_deserialization,
)


def test_deserialization_detects_pickle_loads():
    code = """
import pickle

def load_user_session(raw_data):
    return pickle.loads(raw_data)
"""
    sanitizer = DeserializationSanitizer()
    findings = sanitizer.analyze(code)
    assert len(findings) == 1
    assert findings[0].vulnerable_call == "pickle.loads"
    assert findings[0].risk_severity == "CRITICAL"


def test_deserialization_detects_unsafe_yaml_load():
    code = """
import yaml

def parse_config(content):
    return yaml.load(content)
"""
    sanitizer = DeserializationSanitizer()
    findings = sanitizer.analyze(code)
    assert len(findings) == 1
    assert findings[0].vulnerable_call == "yaml.load"


def test_deserialization_synthesizes_safe_yaml_load():
    code = """
import yaml

def parse_config(content):
    return yaml.load(content)
"""
    healed = sanitize_deserialization(code)
    assert "yaml.safe_load" in healed
