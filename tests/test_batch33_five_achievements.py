import pytest
from healing.yaml_multidoc_safeloader_healer import YamlMultidocSafeloaderHealer
from healing.asyncio_taskgroup_healer import AsyncioTaskgroupHealer
from healing.buffer_overread_guard_sanitizer import safe_buffer_read_slice
from healing.sql_raw_format_param_defuser import SqlRawFormatParamDefuser
from healing.tempfile_directory_race_healer import TempfileDirectoryRaceHealer

def test_achievement_1_yaml_multidoc():
    healer = YamlMultidocSafeloaderHealer()
    code = "docs = yaml.load_all(stream)"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "yaml.safe_load_all(stream)" in healed

def test_achievement_2_asyncio_taskgroup():
    healer = AsyncioTaskgroupHealer()
    code = "results = await asyncio.gather(t1, t2)"
    healed, count = healer.heal_source(code)
    assert count == 1

def test_achievement_3_buffer_overread_guard():
    buffer = b"12345678" # 8 bytes
    # Malicious Heartbleed-style request: claim 64KB when buffer is 8 bytes
    safe = safe_buffer_read_slice(buffer, requested_length=65536, offset=0)
    # Output must strictly clamp to 8 bytes, preventing memory leak
    assert len(safe) == 8
    assert safe == b"12345678"

    # Valid slice
    sliced = safe_buffer_read_slice(buffer, requested_length=4, offset=2)
    assert sliced == b"3456"

def test_achievement_4_sql_raw_format_param():
    healer = SqlRawFormatParamDefuser()
    code = "cursor.execute('SELECT * FROM users WHERE id = ' + user_id)"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "?" in healed
    assert "param" in healed

def test_achievement_5_tempfile_dir_race():
    healer = TempfileDirectoryRaceHealer()
    code = "d = tempfile.mkdtemp()"
    healed, count = healer.heal_source(code)
    assert count == 1
