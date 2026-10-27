import os
import pytest
from healing.path_traversal_healer import PathTraversalHealer, safe_path_jail


@pytest.fixture
def healer():
    return PathTraversalHealer()


def test_safe_path_jail_allows_valid_subpaths(tmp_path):
    subfile = tmp_path / "valid.txt"
    subfile.write_text("safe content")

    resolved = safe_path_jail(str(tmp_path), "valid.txt")
    assert resolved == os.path.realpath(str(subfile))


def test_safe_path_jail_blocks_directory_traversal(tmp_path):
    with pytest.raises(PermissionError, match="Path traversal escape attempt"):
        safe_path_jail(str(tmp_path), "../../etc/shadow")


def test_safe_path_jail_blocks_absolute_escape(tmp_path):
    with pytest.raises(PermissionError, match="Path traversal escape attempt"):
        safe_path_jail(str(tmp_path), "/etc/passwd")


def test_heals_open_os_path_join(healer, tmp_path):
    vulnerable_code = """
import os

def read_user_report(base_dir, filename):
    with open(os.path.join(base_dir, filename), "r") as f:
        return f.read()
"""
    healed, count = healer.heal_source(vulnerable_code)
    assert count == 1
    assert "_autocure_safe_path(base_dir, filename)" in healed
    assert "def _autocure_safe_path" in healed

    # Execute the healed code in a fresh namespace to verify runtime protection
    scope = {}
    exec(healed, scope)
    read_func = scope["read_user_report"]

    # Valid file should work
    test_file = tmp_path / "report.csv"
    test_file.write_text("revenue,100")
    assert read_func(str(tmp_path), "report.csv") == "revenue,100"

    # Traversal attempt must be blocked
    with pytest.raises(PermissionError, match="Path traversal escape attempt"):
        read_func(str(tmp_path), "../../../etc/passwd")


def test_leaves_safe_static_open_unmodified(healer):
    safe_code = """
def read_system_config():
    with open("/etc/hosts", "r") as f:
        return f.read()
"""
    healed, count = healer.heal_source(safe_code)
    assert count == 0
    assert healed.strip() == safe_code.strip()
