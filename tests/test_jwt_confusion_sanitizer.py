import pytest
from healing.jwt_confusion_sanitizer import JWTConfusionSanitizer, sanitize_jwt_confusion


def test_jwt_detects_missing_algorithms():
    code = """
import jwt

def verify_token(raw_jwt):
    return jwt.decode(raw_jwt, "secret_key")
"""
    sanitizer = JWTConfusionSanitizer()
    findings = sanitizer.analyze(code)
    assert len(findings) == 1
    assert "without explicit algorithms" in findings[0].vulnerable_operation


def test_jwt_detects_none_algorithm():
    code = """
import jwt

def verify_token(raw_jwt):
    return jwt.decode(raw_jwt, "secret_key", algorithms=["HS256", "none"])
"""
    sanitizer = JWTConfusionSanitizer()
    findings = sanitizer.analyze(code)
    assert len(findings) == 1
    assert findings[0].risk_severity == "CRITICAL"


def test_jwt_clean_code_passes():
    code = """
import jwt

def verify_token(raw_jwt):
    return jwt.decode(raw_jwt, "public_key", algorithms=["RS256"])
"""
    sanitizer = JWTConfusionSanitizer()
    findings = sanitizer.analyze(code)
    assert len(findings) == 0
