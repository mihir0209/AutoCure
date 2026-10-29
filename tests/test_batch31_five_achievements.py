import pytest
from healing.ssl_verification_false_healer import SslVerificationFalseHealer
from healing.named_tempfile_delete_healer import NamedTempfileDeleteHealer
from healing.os_environ_secret_leak_scrubber import scrub_sensitive_environ_strings
from healing.multiprocessing_poison_pill_injector import MultiprocessingPoisonPillInjector
from healing.xml_billion_laughs_defuser import defuse_xml_billion_laughs_entities

def test_achievement_1_ssl_verification_healer():
    healer = SslVerificationFalseHealer()
    code = "resp = requests.get('https://api.internal', verify=False)"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "verify=True" in healed

def test_achievement_2_named_tempfile_delete():
    healer = NamedTempfileDeleteHealer()
    code = "f = tempfile.NamedTemporaryFile(delete=False)"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "delete=True" in healed

def test_achievement_3_os_environ_secret_scrubber():
    raw_log = "Error in worker: API_KEY='sk-ant-api03-abcdef123456789' and password: 'SuperSecretPassword99'"
    scrubbed = scrub_sensitive_environ_strings(raw_log)
    assert "sk-ant-api03" not in scrubbed
    assert "SuperSecretPassword99" not in scrubbed
    assert "API_KEY=[REDACTED_SECRET]" in scrubbed

def test_achievement_4_poison_pill_injector():
    healer = MultiprocessingPoisonPillInjector()
    code = "def worker_loop(queue): pass"
    healed, count = healer.heal_source(code)
    assert count == 1

def test_achievement_5_billion_laughs_defuser():
    xml_bomb = """<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol2 "&lol;&lol;&lol;&lol;">
]>
<data>&lol2;</data>"""
    defused = defuse_xml_billion_laughs_entities(xml_bomb)
    assert "<!ENTITY" not in defused
    assert "<data>&lol2;</data>" in defused
