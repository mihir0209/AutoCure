import pytest
from healing.xxe_defusal_healer import XxeDefusalHealer
from healing.flask_secret_key_guard import enforce_secure_flask_secret
from healing.eval_literal_healer import EvalToLiteralHealer
from healing.tempfile_suffix_jail import sanitize_tempfile_suffix
from healing.subprocess_env_scrubber import scrub_subprocess_env

def test_achievement_1_xxe_defusal():
    healer = XxeDefusalHealer()
    code = "parser = lxml.etree.XMLParser()"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "resolve_entities=False" in healed
    assert "no_network=True" in healed

def test_achievement_2_flask_secret_guard():
    # Weak secret gets upgraded to 64-char hex (256-bit)
    weak = "weak123"
    secured = enforce_secure_flask_secret(weak)
    assert len(secured) == 64
    assert secured != weak

    # Strong 32+ char secret stays unchanged
    strong = "this_is_a_sufficiently_long_secret_key_over_32_bytes"
    assert enforce_secure_flask_secret(strong) == strong

def test_achievement_3_eval_literal_healer():
    healer = EvalToLiteralHealer()
    code = "data = eval(untrusted_str)"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "ast.literal_eval(untrusted_str)" in healed

def test_achievement_4_tempfile_suffix_jail():
    assert sanitize_tempfile_suffix("../../etc/passwd") == ".tmp"
    assert sanitize_tempfile_suffix("/evil.sh") == ".tmp"
    assert sanitize_tempfile_suffix("csv") == ".csv"
    assert sanitize_tempfile_suffix(".json") == ".json"

def test_achievement_5_subprocess_env_scrubber():
    env = {
        "PATH": "/usr/bin",
        "LD_PRELOAD": "/tmp/malicious.so",
        "PYTHONPATH": "/evil/lib",
        "USER": "app",
    }
    scrubbed = scrub_subprocess_env(env)
    assert "LD_PRELOAD" not in scrubbed
    assert "PYTHONPATH" not in scrubbed
    assert scrubbed["PATH"] == "/usr/bin"
    assert scrubbed["USER"] == "app"
