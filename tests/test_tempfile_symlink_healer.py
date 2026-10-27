import os
import pytest
from healing.tempfile_symlink_healer import TempfileSymlinkHealer, safe_tempfile_open


@pytest.fixture
def healer():
    return TempfileSymlinkHealer()


def test_safe_tempfile_open_creates_file_safely(tmp_path):
    target = tmp_path / "test_safe.txt"
    with safe_tempfile_open(str(target), "w") as f:
        f.write("safe payload")

    assert target.read_text() == "safe payload"
    # Strict 0o600 permissions check
    mode = os.stat(str(target)).st_mode & 0o777
    assert mode == 0o600


def test_safe_tempfile_blocks_overwriting_existing_race_file(tmp_path):
    target = tmp_path / "pre_existing.txt"
    target.write_text("initial")

    with pytest.raises(PermissionError, match="already exists or is a symlink"):
        safe_tempfile_open(str(target), "w")


def test_safe_tempfile_blocks_symlink_attack(tmp_path):
    victim = tmp_path / "victim_data.txt"
    victim.write_text("critical secret")

    # Attacker places symlink at /tmp target pointing to victim
    symlink_target = tmp_path / "attacker_symlink"
    os.symlink(str(victim), str(symlink_target))

    with pytest.raises(PermissionError, match="already exists or is a symlink"):
        safe_tempfile_open(str(symlink_target), "w")

    # Verify victim data was not overwritten
    assert victim.read_text() == "critical secret"


def test_heals_vulnerable_open_tmp_call(healer, tmp_path):
    vulnerable_code = """
def write_cache(data):
    with open("/tmp/app_cache.json", "w") as f:
        f.write(data)
"""
    healed, count = healer.heal_source(vulnerable_code)
    assert count == 1
    assert "_autocure_safe_temp_open('/tmp/app_cache.json', 'w')" in healed
    assert "def _autocure_safe_temp_open" in healed


def test_heals_dynamic_fstring_tmp_path(healer):
    vulnerable_code = """
def dump_user_session(uid, data):
    with open(f"/tmp/session_{uid}.dat", "w") as f:
        f.write(data)
"""
    healed, count = healer.heal_source(vulnerable_code)
    assert count == 1
    assert "_autocure_safe_temp_open" in healed


def test_leaves_safe_non_tmp_file_open_unmodified(healer):
    safe_code = """
def write_local_log():
    with open("logs/application.log", "a") as f:
        f.write("ready")
"""
    healed, count = healer.heal_source(safe_code)
    assert count == 0
    assert healed.strip() == safe_code.strip()
