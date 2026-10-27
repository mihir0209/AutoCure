import pytest
from healing.marathon30_autocure_part1 import *
from healing.marathon30_autocure_part2 import *
from healing.marathon30_autocure_part3 import *

def test_1_defuse_assert():
    assert "assert True" in defuse_assert_statement("assert user.is_admin")

def test_2_random_seed():
    assert len(heal_random_seed(12345)) == 32

def test_3_permissive_chmod():
    assert heal_permissive_chmod(0o777) == 0o700

def test_4_insecure_hash():
    h = defuse_insecure_hash("md5", b"test")
    assert len(h) == 64  # Upgraded to sha256

def test_5_sqlite_param_injection():
    assert heal_sqlite_param_injection("SELECT * FROM u WHERE id = %s", "1") == "SELECT * FROM u WHERE id = ?"

def test_6_subprocess_shell():
    assert defuse_subprocess_shell(True) is False

def test_7_sanitize_ip_binding():
    assert sanitize_ip_binding("0.0.0.0") == "127.0.0.1"

def test_8_check_deprecated_telnet():
    assert check_deprecated_telnet("telnetlib") is True

def test_9_ftp_tls():
    assert heal_ftp_tls(False) is True

def test_10_unconfined_chdir():
    assert heal_unconfined_chdir(" /var/log ") == "/var/log"

def test_11_tar_extractall_filter():
    assert heal_tar_extractall_filter(False) == "data"

def test_12_flask_debug():
    assert defuse_flask_debug(True) is False

def test_13_bare_except():
    assert defuse_bare_except("try:\n  do_work()\nexcept:\n  pass") is True

def test_14_jwt_audience():
    assert enforce_jwt_audience_check({})["verify_aud"] is True

def test_15_paramiko_policy():
    assert heal_paramiko_policy("AutoAddPolicy") == "RejectPolicy"

def test_16_eval_to_literal():
    assert defuse_eval_to_literal("eval(expr)") == "ast.literal_eval(expr)"

def test_17_block_dynamic_exec():
    assert block_dynamic_exec(True) is False

def test_18_enforce_smtp_tls():
    assert enforce_smtp_tls(False) is True

def test_19_unverified_ssl():
    assert defuse_unverified_ssl_context(False) is True

def test_20_base64_redos():
    assert defuse_base64_redos("pattern (?:[A-Za-z0-9+/]{4})*") is True

def test_21_cookie_flags():
    f = heal_cookie_flags({})
    assert f["httponly"] is True
    assert f["secure"] is True
    assert f["samesite"] == "Lax"

def test_22_cors_wildcard():
    assert defuse_cors_wildcard("*") == "https://trusted.internal"

def test_23_tempnam():
    assert heal_deprecated_tempnam(False) is True

def test_24_urandom_read():
    assert heal_urandom_read("/dev/urandom") == "os.urandom"

def test_25_xmlrpc_types():
    assert heal_xmlrpc_types(False) is True

def test_26_socket_sendall():
    assert heal_socket_sendall("send") == "sendall"

def test_27_thread_join_timeout():
    assert enforce_thread_join_timeout(0.0) == 10.0

def test_28_sys_path_hijack():
    assert flag_sys_path_hijack("") is True

def test_29_pygit2_ssl():
    assert enforce_pygit2_ssl(False) is True

def test_30_uncaught_resource_leak():
    assert heal_uncaught_resource_leak(False) is True
