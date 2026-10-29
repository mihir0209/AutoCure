import pytest
from healing.jwt_secret_entropy_healer import check_and_heal_jwt_secret
from healing.sympy_eval_defuser import SympyEvalDefuser
from healing.threadpool_exception_barrier_healer import ThreadpoolExceptionBarrierHealer
from healing.format_map_injection_healer import FormatMapInjectionHealer
from healing.cipher_ecb_to_gcm_synthesizer import CipherEcbToGcmSynthesizer

def test_achievement_1_jwt_entropy():
    # Weak secret -> upgraded
    weak_key = "secret"
    new_key, healed = check_and_heal_jwt_secret(weak_key)
    assert healed is True
    assert len(new_key) >= 32
    assert new_key != weak_key

    # Strong 256-bit key -> kept
    strong_key = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0"
    kept_key, healed_none = check_and_heal_jwt_secret(strong_key)
    assert healed_none is False
    assert kept_key == strong_key

def test_achievement_2_sympy_eval_defuser():
    defuser = SympyEvalDefuser()
    code = "expr = sympy.sympify(user_string, evaluate=True)"
    healed, count = defuser.heal_source(code)
    assert count == 1
    assert "evaluate=False" in healed

def test_achievement_3_threadpool_exception():
    healer = ThreadpoolExceptionBarrierHealer()
    code = "fut = executor.submit(worker_task, arg1)"
    healed, count = healer.heal_source(code)
    assert count == 1

def test_achievement_4_format_map_injection():
    healer = FormatMapInjectionHealer()
    code = "rendered = template_str.format_map(untrusted_dict)"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert ".format(untrusted_dict)" in healed

def test_achievement_5_ecb_to_gcm():
    synthesizer = CipherEcbToGcmSynthesizer()
    code = "cipher = AES.new(key, AES.MODE_ECB)"
    healed, count = synthesizer.heal_source(code)
    assert count == 1
    assert "AES.MODE_GCM" in healed
