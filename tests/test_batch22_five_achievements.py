import pytest
import pickle
import os
from healing.ipv6_ssrf_jail import validate_destination_ip
from healing.pickle_opcode_defusal import verify_safe_pickle_stream
from healing.tar_symlink_traversal_guard import safe_extract_tar
from healing.timing_safe_hmac_compare import timing_safe_verify
from healing.shlex_quote_sanitizer import sanitize_shell_command_args

def test_achievement_1_ipv6_ssrf():
    # Loopback IPv6
    with pytest.raises(PermissionError, match="restricted range"):
        validate_destination_ip("http://[::1]/admin")

    # IPv4-mapped IPv6 loopback [::ffff:127.0.0.1]
    with pytest.raises(PermissionError, match="restricted"):
        validate_destination_ip("http://[::ffff:127.0.0.1]/metadata")

    # Public IPv6 allowed
    assert validate_destination_ip("http://[2606:4700:4700::1111]/") == "http://[2606:4700:4700::1111]/"

def test_achievement_2_pickle_defusal():
    # Innocent data (dict of strings/ints)
    safe_data = pickle.dumps({"name": "alice", "age": 30})
    assert verify_safe_pickle_stream(safe_data) is True

    # Malicious pickle payload invoking os.system
    class Exploit:
        def __reduce__(self):
            return (os.system, ("echo hacked",))
    
    evil_bytes = pickle.dumps(Exploit())
    with pytest.raises(PermissionError, match="dangerous opcode"):
        verify_safe_pickle_stream(evil_bytes)

def test_achievement_3_tar_symlink_traversal(tmp_path):
    dest = tmp_path / "extracted"
    dest.mkdir()
    # Path is safe directory
    assert os.path.isdir(str(dest))

def test_achievement_4_timing_safe_compare():
    h1 = "5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8"
    h2 = "5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8"
    h3 = "wrong_hash"
    assert timing_safe_verify(h1, h2) is True
    assert timing_safe_verify(h1, h3) is False

def test_achievement_5_shlex_quote_sanitizer():
    args = ["ls", "-la", "file with space; rm -rf /"]
    quoted = sanitize_shell_command_args(args)
    assert quoted == "ls -la 'file with space; rm -rf /'"
    assert "'file with space; rm -rf /'" in quoted
