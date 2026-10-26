"""Unit and Regression Tests for SSRF AST Sanitizer."""

import pytest
from healing.ssrf_sanitizer import (
    SSRFFinding,
    SSRFSanitizer,
    sanitize_ssrf,
)


def test_ssrf_detects_dynamic_request_url():
    code = """
import requests

def fetch_webhook(webhook_url: str):
    response = requests.get(webhook_url)
    return response.json()
"""
    engine = SSRFSanitizer()
    findings = engine.analyze(code)
    assert len(findings) == 1
    assert findings[0].client_method == "get"
    assert findings[0].url_arg_name == "webhook_url"
    assert "SSRF" in findings[0].vulnerability_reason


def test_ssrf_synthesizes_safe_url_guard():
    code = """
import requests

def download_asset(target_url: str):
    return requests.get(target_url)
"""
    healed, findings = sanitize_ssrf(code)
    assert len(findings) == 1
    assert "validate_safe_url(target_url)" in healed

    # Verify compilation and invocation with mock validator
    compiled = compile(healed, "<test>", "exec")
    calls = []
    namespace = {
        "validate_safe_url": lambda u: calls.append(u) or u,
    }
    exec(compiled, namespace)
    namespace["requests"] = type("Req", (), {"get": lambda self, url: f"Fetched {url}"})()
    res = namespace["download_asset"]("https://api.example.com/data")
    assert res == "Fetched https://api.example.com/data"
    assert calls == ["https://api.example.com/data"]


def test_ssrf_ignores_constant_trusted_urls():
    code = """
import requests

def get_system_health():
    return requests.get("https://internal.company.com/health")
"""
    healed, findings = sanitize_ssrf(code)
    assert len(findings) == 0
    assert healed.strip() == code.strip()
