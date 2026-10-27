import pytest
from healing.open_redirect_healer import OpenRedirectHealer, safe_redirect


@pytest.fixture
def healer():
    return OpenRedirectHealer()


def test_safe_redirect_preserves_valid_local_relative_paths():
    assert safe_redirect("/dashboard") == "/dashboard"
    assert safe_redirect("/settings/profile?tab=security") == "/settings/profile?tab=security"


def test_safe_redirect_neutralizes_open_redirect_attacks():
    # External attacker domain
    assert safe_redirect("https://evil-phishing.com/login", allowed_hosts={"mysite.com"}) == "/"

    # Protocol-relative URLs
    assert safe_redirect("//evil.com/payload") == "/"
    assert safe_redirect("/\\evil.com") == "/"

    # Dangerous non-http schemes
    assert safe_redirect("javascript:alert(document.cookie)") == "/"
    assert safe_redirect("data:text/html,<script>alert(1)</script>") == "/"


def test_safe_redirect_allows_explicit_allowlisted_domains():
    allowed = {"trusted-partner.com", "mysite.com"}
    assert safe_redirect("https://trusted-partner.com/oauth/callback", allowed_hosts=allowed) == "https://trusted-partner.com/oauth/callback"
    assert safe_redirect("https://sub.mysite.com/portal", allowed_hosts=allowed) == "https://sub.mysite.com/portal"


def test_heals_vulnerable_redirect_call(healer):
    vulnerable_code = """
# mock redirect

def login_handler(request):
    next_url = request.args.get("next")
    return redirect(next_url)
"""
    healed, count = healer.heal_source(vulnerable_code)
    assert count == 1
    assert "_autocure_safe_redirect(next_url)" in healed
    assert "def _autocure_safe_redirect" in healed

    # Execute the healed code in a sandbox
    scope = {"redirect": lambda u: f"Redirected to: {u}"}
    exec(healed, scope)
    handler = scope["login_handler"]

    # Mock request with malicious next_url
    class MockRequest:
        args = {"next": "//evil.com/steal-creds"}

    res = handler(MockRequest())
    assert res == "Redirected to: /"


def test_leaves_safe_static_redirect_unmodified(healer):
    safe_code = """
# mock redirect

def logout():
    return redirect("/login")
"""
    healed, count = healer.heal_source(safe_code)
    assert count == 0
    assert healed.strip() == safe_code.strip()
