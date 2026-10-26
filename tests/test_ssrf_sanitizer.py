import pytest
from healing.ssrf_sanitizer import SSRFSanitizer, is_safe_url


def test_ssrf_detects_dynamic_requests_get():
    code = """
import requests

def fetch_webhook(url):
    response = requests.get(url, timeout=5)
    return response.text
"""
    sanitizer = SSRFSanitizer()
    findings = sanitizer.analyze(code)
    assert len(findings) == 1
    assert "requests.get" in findings[0].vulnerable_call


def test_is_safe_url_blocks_private_and_loopback_ips():
    assert not is_safe_url("http://127.0.0.1/admin")
    assert not is_safe_url("http://localhost:8080/metrics")
    assert not is_safe_url("http://169.254.169.254/latest/meta-data/")
    assert not is_safe_url("http://10.0.0.1/internal")
    assert not is_safe_url("http://192.168.1.1/router")
    assert not is_safe_url("ftp://malicious.com/file")


def test_is_safe_url_allows_public_web_targets():
    assert is_safe_url("https://api.github.com/repos")
    assert is_safe_url("https://example.com/data")
    assert is_safe_url("http://93.184.216.34/index.html")
