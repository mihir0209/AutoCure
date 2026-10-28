import pytest
import pathlib
import os
from healing.static_crypto_salt_healer import StaticCryptoSaltHealer
from healing.asyncio_cancellation_barrier_healer import AsyncioCancellationBarrierHealer
from healing.insecure_random_secrets_healer import InsecureRandomSecretsHealer
from healing.redos_atomic_group_sanitizer import sanitize_nested_redos_pattern
from healing.pathlib_directory_jail_healer import safe_resolve_pathlib_jail

def test_achievement_1_static_crypto_salt():
    healer = StaticCryptoSaltHealer()
    code = "cipher = AES.new(key, AES.MODE_CBC, b'1234567890123456')"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "os.urandom(16)" in healed

def test_achievement_2_asyncio_barrier():
    healer = AsyncioCancellationBarrierHealer()
    code = "async def worker(): pass"
    healed, count = healer.heal_source(code)
    assert count == 1

def test_achievement_3_insecure_random_secrets():
    healer = InsecureRandomSecretsHealer()
    code = "tok = random.choice(alphabet)"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "secrets.choice(alphabet)" in healed

def test_achievement_4_redos_atomic_sanitizer():
    evil = r"^([a-z]+)+$"
    clean = sanitize_nested_redos_pattern(evil)
    assert "([" not in clean or ")+" not in clean
    assert "[a-z]+" in clean

def test_achievement_5_pathlib_jail(tmp_path):
    root = tmp_path / "sandbox"
    root.mkdir()
    safe_file = root / "report.txt"
    safe_file.write_text("ok")

    # Safe path inside jail
    resolved = safe_resolve_pathlib_jail("report.txt", str(root))
    assert resolved == safe_file.resolve()

    # Escape attempt
    with pytest.raises(PermissionError, match="Pathlib jail escape"):
        safe_resolve_pathlib_jail("../../etc/passwd", str(root))
