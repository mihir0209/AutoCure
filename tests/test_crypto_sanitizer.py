"""Unit and Regression Tests for Cryptographic Weakness AST Sanitizer."""

import hashlib
import pytest
from healing.crypto_sanitizer import (
    CryptoFinding,
    CryptoSanitizer,
    sanitize_crypto,
)


def test_crypto_detects_broken_md5():
    code = """
import hashlib

def hash_password(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest()
"""
    engine = CryptoSanitizer()
    findings = engine.analyze(code)
    assert len(findings) == 1
    assert "MD5" in findings[0].vulnerability_reason
    assert findings[0].weak_primitive == "hashlib.md5"


def test_crypto_synthesizes_sha256_upgrade():
    code = """
import hashlib

def create_checksum(data: bytes):
    return hashlib.md5(data)
"""
    healed, findings = sanitize_crypto(code)
    assert len(findings) == 1
    assert "hashlib.sha256(data)" in healed

    # Verify execution
    compiled = compile(healed, "<test>", "exec")
    namespace = {"hashlib": hashlib}
    exec(compiled, namespace)
    res = namespace["create_checksum"](b"test_data")
    assert res.name == "sha256"


def test_crypto_allows_explicit_usedforsecurity_false():
    code = """
import hashlib

def non_sec_etag(data):
    return hashlib.md5(data, usedforsecurity=False)
"""
    healed, findings = sanitize_crypto(code)
    assert len(findings) == 0
    assert healed.strip() == code.strip()
