import pytest
from healing.pickle_hmac_wrapper_healer import PickleHmacWrapperHealer
from healing.asyncio_semaphore_fairness_healer import AsyncioSemaphoreFairnessHealer
from healing.unbounded_upload_spooler_healer import UnboundedUploadSpoolerHealer
from healing.subprocess_shell_injection_sanitizer import SubprocessShellInjectionSanitizer
from healing.assert_statement_production_healer import AssertStatementProductionHealer

def test_achievement_1_pickle_wrapper():
    healer = PickleHmacWrapperHealer()
    code = "obj = pickle.loads(untrusted_payload)"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "json.loads(untrusted_payload)" in healed

def test_achievement_2_asyncio_semaphore():
    healer = AsyncioSemaphoreFairnessHealer()
    code = "sem = asyncio.Semaphore(5)"
    healed, count = healer.heal_source(code)
    assert count == 1

def test_achievement_3_unbounded_spooler():
    healer = UnboundedUploadSpoolerHealer()
    code = "buf = io.BytesIO()"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "tempfile.SpooledTemporaryFile(max_size=10485760)" in healed

def test_achievement_4_subprocess_shell_sanitizer():
    healer = SubprocessShellInjectionSanitizer()
    code = "subprocess.run(['ls', '-la'], shell=True)"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "shell=False" in healed

def test_achievement_5_assert_statement_healer():
    healer = AssertStatementProductionHealer()
    code = "assert user.is_authenticated, 'User must be authenticated'"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "if not user.is_authenticated:" in healed
    assert "raise AssertionError('User must be authenticated')" in healed
