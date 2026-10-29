import pytest
from healing.dh_weak_subgroup_healer import validate_and_heal_dh_public_key
from healing.asyncio_loop_closed_leak_healer import AsyncioLoopClosedLeakHealer
from healing.http_crlf_header_injection_defuser import sanitize_http_header_value
from healing.marshmallow_strict_validation_healer import MarshmallowStrictValidationHealer
from healing.multiprocessing_pipe_hmac_guard import verify_and_unpack_pipe_message

def test_achievement_1_dh_subgroup():
    # Valid safe prime p = 23, generator g = 5, subgroup order q = 11
    # 5^11 mod 23 == 22 != 1. For p=23, q=11, valid elements are quadratic residues y: y^11 mod 23 == 1
    # For example, y = 4 (since 4 = 2^2 mod 23) -> 4^11 mod 23 = pow(4, 11, 23) = 1
    assert validate_and_heal_dh_public_key(4, 23, 11) is True

    # Invalid public key y = 1 (violates 2 <= y <= p-2)
    assert validate_and_heal_dh_public_key(1, 23, 11) is False

    # Invalid subgroup element y = 2 -> pow(2, 11, 23) = 22 != 1
    assert validate_and_heal_dh_public_key(5, 23, 11) is False

def test_achievement_2_asyncio_loop_closed():
    healer = AsyncioLoopClosedLeakHealer()
    code = "loop.run_until_complete(main())"
    healed, count = healer.heal_source(code)
    assert count == 1

def test_achievement_3_http_crlf_injection():
    malicious_header = "en-US\r\nSet-Cookie: session_admin_compromise=1\r\n"
    clean = sanitize_http_header_value(malicious_header)
    assert "\r" not in clean
    assert "\n" not in clean
    assert clean == "en-USSet-Cookie: session_admin_compromise=1"

def test_achievement_4_marshmallow_strict():
    healer = MarshmallowStrictValidationHealer()
    code = """
class UserSchema(Schema):
    name = fields.Str()
"""
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "class Meta:" in healed
    assert "unknown = EXCLUDE" in healed

def test_achievement_5_pipe_hmac_guard():
    secret = b"cluster_ipc_secret_key_32bytes!"
    import hashlib, hmac
    payload = b"AUTHENTIC_WORKER_IPC_DATA"
    sig = hmac.new(secret, payload, hashlib.sha256).digest()
    wire_msg = sig + payload

    # Authentic message
    valid, data = verify_and_unpack_pipe_message(wire_msg, secret)
    assert valid is True
    assert data == payload

    # Tampered message
    tampered_msg = sig + b"TAMPERED_DATA"
    valid_t, _ = verify_and_unpack_pipe_message(tampered_msg, secret)
    assert valid_t is False
