import pytest
import os
from healing.sql_like_sanitizer import sanitize_like_pattern
from healing.tempdir_jail_healer import create_isolated_tempdir
from healing.jwt_key_length_guard import validate_jwt_key_length
from healing.subprocess_path_sanitizer import sanitize_executable_path
from healing.json_depth_jail import parse_json_with_depth_limit

def test_achievement_1_sql_like_sanitizer():
    # Escapes % and _ to prevent wildcard injection
    raw = "admin%_test\\done"
    sanitized = sanitize_like_pattern(raw)
    assert "\\%" in sanitized
    assert "\\_" in sanitized
    assert "\\\\" in sanitized

def test_achievement_2_tempdir_jail():
    temp_dir = create_isolated_tempdir("test_jail_")
    assert os.path.isdir(temp_dir)
    mode = os.stat(temp_dir).st_mode & 0o777
    assert mode == 0o700
    os.rmdir(temp_dir)

def test_achievement_3_jwt_key_length():
    # Short 16-byte key fails
    with pytest.raises(ValueError, match="below 256-bit requirement"):
        validate_jwt_key_length("HS256", "short_secret_key_16b")

    # Secure 32-byte key passes
    assert validate_jwt_key_length("HS256", "this_is_a_very_secure_32_byte_key!!") is True

def test_achievement_4_subprocess_path_sanitizer():
    # Resolves 'python3' to absolute path
    path = sanitize_executable_path("python3")
    assert os.path.isabs(path)
    assert os.path.exists(path)

    with pytest.raises(FileNotFoundError):
        sanitize_executable_path("non_existent_binary_xyz_123")

def test_achievement_5_json_depth_jail():
    # Deeply nested JSON: 10 levels deep with max_depth 5
    nested_json = '{"a": {"b": {"c": {"d": {"e": {"f": 1}}}}}}'
    with pytest.raises(ValueError, match="exceeds maximum allowed depth"):
        parse_json_with_depth_limit(nested_json, max_depth=4)

    # Shallow JSON passes
    valid = parse_json_with_depth_limit('{"user": "alice", "roles": [1, 2]}', max_depth=4)
    assert valid["user"] == "alice"
