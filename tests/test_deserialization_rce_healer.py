import pytest
from healing.deserialization_rce_healer import heal_deserialization_vulnerabilities

def test_heal_pickle_loads():
    vuln_code = """
import pickle

def handle_request(payload):
    obj = pickle.loads(payload)
    return obj
"""
    healed, count, findings = heal_deserialization_vulnerabilities(vuln_code)
    assert count == 1
    assert "json.loads(payload)" in healed
    assert "pickle.loads" not in healed

def test_heal_unsafe_yaml_load():
    vuln_code = """
import yaml

def parse_config(raw_yaml):
    cfg = yaml.load(raw_yaml)
    return cfg
"""
    healed, count, findings = heal_deserialization_vulnerabilities(vuln_code)
    assert count == 1
    assert "yaml.safe_load(raw_yaml)" in healed

def test_leave_safe_yaml_intact():
    safe_code = """
import yaml

def parse_config(raw_yaml):
    cfg = yaml.load(raw_yaml, Loader=yaml.SafeLoader)
    return cfg
"""
    healed, count, findings = heal_deserialization_vulnerabilities(safe_code)
    assert count == 0
