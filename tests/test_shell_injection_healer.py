import ast
import pytest
from healing.shell_injection_healer import ShellInjectionHealer


@pytest.fixture
def healer():
    return ShellInjectionHealer()


def test_heals_subprocess_run_shell_true(healer):
    vulnerable_code = """
import subprocess

def execute_user_task(user_arg):
    return subprocess.run(f"ping -c 1 {user_arg}", shell=True)
"""
    healed, count = healer.heal_source(vulnerable_code)
    assert count == 1
    assert "shell=False" in healed
    assert "shlex.split" in healed
    assert "import shlex" in healed

    # Verify syntax validity
    compiled = compile(healed, "<test>", "exec")
    assert compiled is not None


def test_heals_subprocess_popen_shell_true(healer):
    vulnerable_code = """
import subprocess

def run_background_daemon(cmd_str):
    p = subprocess.Popen(cmd_str, shell=True, stdout=subprocess.PIPE)
    return p
"""
    healed, count = healer.heal_source(vulnerable_code)
    assert count == 1
    assert "shell=False" in healed
    assert "shlex.split(cmd_str)" in healed
    assert compile(healed, "<test>", "exec") is not None


def test_heals_os_system_legacy_call(healer):
    vulnerable_code = """
import os

def cleanup_temp(filename):
    os.system(f"rm -rf /tmp/{filename}")
"""
    healed, count = healer.heal_source(vulnerable_code)
    assert count == 1
    assert "subprocess.run(shlex.split(" in healed
    assert "import shlex" in healed
    assert "import subprocess" in healed
    assert compile(healed, "<test>", "exec") is not None


def test_leaves_safe_calls_unmodified(healer):
    safe_code = """
import subprocess

def run_safe_list():
    return subprocess.run(["ls", "-l", "/data"], shell=False)
"""
    healed, count = healer.heal_source(safe_code)
    assert count == 0
    assert healed.strip() == safe_code.strip()


def test_leaves_list_args_unmodified_when_shell_true_cleared(healer):
    # Even if shell=True is passed with a list, shell is set to False but list is not re-wrapped with shlex.split
    code = """
import subprocess

def run_list_with_bad_flag():
    return subprocess.run(["grep", "foo", "bar.txt"], shell=True)
"""
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "shell=False" in healed
    assert "shlex.split" not in healed
    assert compile(healed, "<test>", "exec") is not None
