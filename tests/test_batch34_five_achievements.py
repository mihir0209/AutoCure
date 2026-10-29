import pytest
import pathlib
from healing.cbc_padding_oracle_defuser import CbcPaddingOracleDefuser
from healing.threadpool_shutdown_leak_healer import ThreadpoolShutdownLeakHealer
from healing.subprocess_path_env_sanitizer import sanitize_subprocess_path_env
from healing.pandas_query_injection_transformer import PandasQueryInjectionTransformer
from healing.pathlib_symlink_jail_healer import safe_resolve_symlink_jail

def test_achievement_1_cbc_padding_oracle():
    defuser = CbcPaddingOracleDefuser()
    code = "cipher = AES.new(key, AES.MODE_CBC, iv)"
    healed, count = defuser.heal_source(code)
    assert count == 1
    assert "AES.MODE_GCM" in healed

def test_achievement_2_threadpool_shutdown():
    healer = ThreadpoolShutdownLeakHealer()
    code = "executor.shutdown()"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "cancel_futures=True" in healed
    assert "wait=True" in healed

def test_achievement_3_subprocess_path_sanitizer():
    # Insecure PATH with relative '.' and current working directory
    evil_path = ".:/usr/local/bin:./scripts:/usr/bin:bin"
    clean_path = sanitize_subprocess_path_env(evil_path)
    assert "." not in clean_path.split(":")
    assert "./scripts" not in clean_path.split(":")
    assert "/usr/local/bin" in clean_path
    assert "/usr/bin" in clean_path

def test_achievement_4_pandas_query_injection():
    transformer = PandasQueryInjectionTransformer()
    code = "filtered = df.query(f'user_id == {user_input}')"
    healed, count = transformer.heal_source(code)
    assert count == 1
    assert ".filter" in healed

def test_achievement_5_symlink_jail(tmp_path):
    root = tmp_path / "jail"
    root.mkdir()
    safe_file = root / "data.csv"
    safe_file.write_text("ok")

    # Safe access
    resolved = safe_resolve_symlink_jail("data.csv", str(root))
    assert resolved == safe_file.resolve()

    # Symlink traversal escape attempt
    with pytest.raises(PermissionError, match="Symlink jail escape"):
        safe_resolve_symlink_jail("../../../etc/passwd", str(root))
