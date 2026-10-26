import pytest
from healing.insecure_random_sanitizer import (
    find_insecure_random_vulnerabilities, sanitize_random_code
)

def test_detects_random_in_token_generation():
    code = '''
import random

def generate_session_token():
    return str(random.randint(100000, 999999))
'''
    findings = find_insecure_random_vulnerabilities(code)
    assert len(findings) == 1
    assert "secrets" in findings[0].remediation

def test_ignores_non_security_context():
    code = '''
import random

def roll_game_dice():
    return random.randint(1, 6)
'''
    findings = find_insecure_random_vulnerabilities(code)
    assert len(findings) == 0

def test_sanitizes_random_to_secrets():
    code = '''
import random
val = random.randint(0, 100)
chosen = random.choice([1, 2, 3])
'''
    sanitized = sanitize_random_code(code)
    assert "import secrets" in sanitized
    assert "secrets.randbelow" in sanitized
    assert "secrets.choice" in sanitized
