import pytest
from healing.tempfile_toctou_sanitizer import (
    find_tempfile_vulnerabilities, sanitize_tempfile_code
)

def test_detects_insecure_mktemp():
    code = '''
import tempfile

def create_scratch():
    path = tempfile.mktemp()
    with open(path, "w") as f:
        f.write("scratch")
    return path
'''
    findings = find_tempfile_vulnerabilities(code)
    assert len(findings) == 1
    assert findings[0].vulnerability_type == "INSECURE_MKTEMP"
    assert "TOCTOU" in findings[0].remediation

def test_sanitizes_mktemp_call():
    code = '''
import tempfile
path = tempfile.mktemp()
'''
    sanitized = sanitize_tempfile_code(code)
    assert "mktemp()" not in sanitized
    assert "tempfile.NamedTemporaryFile(delete=False).name" in sanitized
