import pytest
from healing.timing_attack_sanitizer import (
    find_timing_attack_vulnerabilities, safe_constant_time_compare
)

def test_detects_non_constant_time_token_check():
    code = '''
def verify_webhook(provided_signature, expected_signature):
    if provided_signature == expected_signature:
        return True
    return False
'''
    findings = find_timing_attack_vulnerabilities(code)
    assert len(findings) == 1
    assert "compare_digest" in findings[0].remediation

def test_safe_constant_time_compare_evaluation():
    assert safe_constant_time_compare("super_secret_token_123", "super_secret_token_123") is True
    assert safe_constant_time_compare("token_a", "token_b") is False
    assert safe_constant_time_compare(b"byte_sig_abc", b"byte_sig_abc") is True
