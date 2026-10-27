import pytest
from healing.ldap_injection_healer import LdapInjectionHealer, ldap_escape_filter


@pytest.fixture
def healer():
    return LdapInjectionHealer()


def test_ldap_escape_filter_escapes_special_characters():
    raw_input = r"admin*)(uid=*))(|(uid=*"
    escaped = ldap_escape_filter(raw_input)
    assert "*" not in escaped
    assert "(" not in escaped
    assert ")" not in escaped
    assert r"\2a" in escaped
    assert r"\28" in escaped
    assert r"\29" in escaped


def test_heals_vulnerable_ldap_query_fstring(healer):
    vulnerable_code = """
def authenticate_user(username):
    search_filter = f"(&(uid={username})(objectClass=person))"
    return search_filter
"""
    healed, count = healer.heal_source(vulnerable_code)
    assert count == 1
    assert "_autocure_ldap_escape(username)" in healed
    assert "def _autocure_ldap_escape" in healed

    # Execute the healed code and verify injection is neutralized
    scope = {}
    exec(healed, scope)
    auth_func = scope["authenticate_user"]

    hostile_input = "*)(uid=*))(|(uid=*"
    result_filter = auth_func(hostile_input)
    assert r"\2a\29\28uid=\2a\29\29\28|\28uid=\2a" in result_filter
    assert "(&(uid=\\2a\\29" in result_filter


def test_heals_multiple_parameters_in_ldap_filter(healer):
    vulnerable_code = """
def lookup_contact(first_name, last_name):
    query = f"(&(cn={first_name}*)(sn={last_name}))"
    return query
"""
    healed, count = healer.heal_source(vulnerable_code)
    assert count == 2
    assert "_autocure_ldap_escape(first_name)" in healed
    assert "_autocure_ldap_escape(last_name)" in healed


def test_leaves_non_ldap_fstring_unmodified(healer):
    benign_code = """
def get_user_profile(user_id):
    return f"https://api.internal/v1/users/{user_id}/profile"
"""
    healed, count = healer.heal_source(benign_code)
    assert count == 0
    assert healed.strip() == benign_code.strip()
