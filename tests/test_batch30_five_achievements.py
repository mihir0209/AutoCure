import pytest
from healing.rsa_key_length_healer import RsaKeyLengthHealer
from healing.tarfile_filter_injector_healer import TarfileFilterInjectorHealer
from healing.generator_exit_resource_healer import GeneratorExitResourceHealer
from healing.ldap_injection_sanitizer import sanitize_ldap_search_filter
from healing.dynamic_dunder_import_healer import DynamicDunderImportHealer

def test_achievement_1_rsa_key_length():
    healer = RsaKeyLengthHealer()
    code = "key = RSA.generate(1024)"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "RSA.generate(3072)" in healed

def test_achievement_2_tarfile_filter():
    healer = TarfileFilterInjectorHealer()
    code = "tar.extractall(path='/tmp/dest')"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "filter='data'" in healed

def test_achievement_3_generator_exit():
    healer = GeneratorExitResourceHealer()
    code = """
def stream_items():
    yield 1
    yield 2
"""
    healed, count = healer.heal_source(code)
    assert count == 1

def test_achievement_4_ldap_injection_sanitizer():
    evil = r"admin*)(uid=*))(|(uid=*"
    sanitized = sanitize_ldap_search_filter(evil)
    assert "*" not in sanitized
    assert "(" not in sanitized
    assert ")" not in sanitized
    assert r"\2a" in sanitized
    assert r"\28" in sanitized

def test_achievement_5_dunder_import_healer():
    healer = DynamicDunderImportHealer()
    code = "mod = __import__(user_module_name)"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "importlib.import_module(user_module_name)" in healed
