import pytest
from healing.secrets_sanitizer import SecretsSanitizer, sanitize_secrets, SecretFinding


def test_secrets_detects_hardcoded_api_key():
    code = """
API_KEY = "sk_live_998877665544332211"

def authenticate():
    return API_KEY
"""
    sanitizer = SecretsSanitizer()
    findings = sanitizer.analyze(code)
    assert len(findings) == 1
    assert findings[0].secret_var == "API_KEY"
    assert "sk_l" in findings[0].masked_secret
    assert "Hardcoded sensitive credential" in findings[0].vulnerability_reason


def test_secrets_detects_aws_secret_key():
    code = """
AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
"""
    sanitizer = SecretsSanitizer()
    findings = sanitizer.analyze(code)
    assert len(findings) == 1
    assert findings[0].secret_var == "AWS_SECRET_ACCESS_KEY"


def test_secrets_synthesizes_os_environ_get():
    bad_code = """
API_KEY = "sk_live_1234567890abcdef"

def get_client():
    return connect(API_KEY)
"""
    healed, findings = sanitize_secrets(bad_code)
    assert len(findings) == 1
    assert "os.environ.get('API_KEY')" in healed or 'os.environ.get("API_KEY")' in healed
    assert "sk_live_" not in healed
    assert "import os" in healed
    compile(healed, "<test>", "exec")


def test_secrets_preserves_existing_os_import():
    bad_code = """
import os

DATABASE_PASSWORD = "SuperSecretPassword123!"

def connect():
    pass
"""
    healed, findings = sanitize_secrets(bad_code)
    assert len(findings) == 1
    assert "DATABASE_PASSWORD = os.environ.get('DATABASE_PASSWORD')" in healed or 'DATABASE_PASSWORD = os.environ.get("DATABASE_PASSWORD")' in healed
    assert healed.count("import os") == 1
    compile(healed, "<test>", "exec")


def test_secrets_ignores_normal_variables():
    clean_code = """
USER_TITLE = "Chief Executive Officer"
APP_NAME = "AutoCure-Enterprise"
MAX_RETRIES = 5
"""
    sanitizer = SecretsSanitizer()
    findings = sanitizer.analyze(clean_code)
    assert len(findings) == 0

    healed, findings = sanitize_secrets(clean_code)
    assert len(findings) == 0
    assert healed == clean_code
