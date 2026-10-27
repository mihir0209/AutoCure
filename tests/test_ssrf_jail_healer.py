import pytest
from healing.ssrf_jail_healer import SSRFJailHealer, ssrf_jail


@pytest.fixture
def healer():
    return SSRFJailHealer()


def test_ssrf_jail_blocks_loopback_and_metadata():
    # Direct loopbacks
    with pytest.raises(PermissionError, match="SSRF blocked"):
        ssrf_jail("http://127.0.0.1:8080/admin")

    with pytest.raises(PermissionError, match="SSRF blocked"):
        ssrf_jail("http://localhost:5000/api")

    # Cloud instance metadata
    with pytest.raises(PermissionError, match="SSRF blocked"):
        ssrf_jail("http://169.254.169.254/latest/meta-data/")


def test_ssrf_jail_blocks_disallowed_schemes():
    with pytest.raises(PermissionError, match="Disallowed scheme"):
        ssrf_jail("file:///etc/passwd")

    with pytest.raises(PermissionError, match="Disallowed scheme"):
        ssrf_jail("gopher://127.0.0.1:6379/_flushall")


def test_ssrf_jail_allows_valid_public_urls():
    # Public domain that resolves cleanly
    url = "https://httpbin.org/get"
    res = ssrf_jail(url)
    assert res == url


def test_heals_dynamic_requests_get(healer):
    vulnerable_code = """
import requests

def fetch_feed(feed_url):
    response = requests.get(feed_url, timeout=5)
    return response.text
"""
    healed, count = healer.heal_source(vulnerable_code)
    assert count == 1
    assert "_autocure_ssrf_jail(feed_url)" in healed
    assert "def _autocure_ssrf_jail" in healed

    # Execute the synthesized healed code in isolation
    scope = {}
    exec(healed, scope)
    fetch_func = scope["fetch_feed"]

    # Attacking AWS metadata via dynamic parameter must raise PermissionError
    with pytest.raises(PermissionError, match="SSRF blocked"):
        fetch_func("http://169.254.169.254/latest/meta-data/")

    # Attacking local admin port must raise PermissionError
    with pytest.raises(PermissionError, match="SSRF blocked"):
        fetch_func("http://127.0.0.1:9000/internal")


def test_heals_urllib_urlopen(healer):
    vulnerable_code = """
import urllib.request

def fetch_data(target_url):
    with urllib.request.urlopen(target_url) as resp:
        return resp.read()
"""
    healed, count = healer.heal_source(vulnerable_code)
    assert count == 1
    assert "_autocure_ssrf_jail(target_url)" in healed


def test_leaves_safe_static_url_unmodified(healer):
    safe_code = """
import requests

def get_status():
    return requests.get("https://api.github.com/status")
"""
    healed, count = healer.heal_source(safe_code)
    assert count == 0
    assert healed.strip() == safe_code.strip()
