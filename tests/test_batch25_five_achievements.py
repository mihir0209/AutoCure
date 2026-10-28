import pytest
from healing.tls_version_disabler_healer import TlsVersionDisablerHealer
from healing.flask_cors_wildcard_sanitizer import FlaskCorsWildcardSanitizer
from healing.subprocess_pipe_deadlock_healer import SubprocessPipeDeadlockHealer
from healing.django_queryset_extra_healer import DjangoQuerySetExtraHealer
from healing.mktemp_deprecation_healer import MktempDeprecationHealer

def test_achievement_1_tls_disabler():
    healer = TlsVersionDisablerHealer()
    code = "ctx = ssl.SSLContext(ssl.PROTOCOL_TLSv1)"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "ssl.PROTOCOL_TLS_CLIENT" in healed

def test_achievement_2_cors_wildcard_sanitizer():
    healer = FlaskCorsWildcardSanitizer(fallback_origin="https://app.example.com")
    code = "CORS(app, origins='*')"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "https://app.example.com" in healed

def test_achievement_3_pipe_deadlock_healer():
    healer = SubprocessPipeDeadlockHealer()
    code = "out = proc.stdout.read()"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "proc.communicate()[0]" in healed

def test_achievement_4_django_extra_healer():
    healer = DjangoQuerySetExtraHealer()
    code = "users = User.objects.extra(select={'is_recent': 'val'})"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "User.objects.annotate(" in healed

def test_achievement_5_mktemp_deprecation_healer():
    healer = MktempDeprecationHealer()
    code = "tmp = tempfile.mktemp()"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "tempfile.NamedTemporaryFile()" in healed
