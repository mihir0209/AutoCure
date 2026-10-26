import pytest
from healing.command_injection_sanitizer import (
    CommandInjectionSanitizer,
    sanitize_command_injection,
    CommandInjectionFinding,
)


def test_command_injection_detects_unsafe_os_system():
    bad_code = """
import os

def ping_host(user_input):
    os.system("ping -c 1 " + user_input)
"""
    sanitizer = CommandInjectionSanitizer()
    findings = sanitizer.analyze(bad_code)
    assert len(findings) == 1
    assert findings[0].vulnerable_call == "os.system"
    assert "arbitrary command injection" in findings[0].vulnerability_reason


def test_command_injection_detects_subprocess_shell_true():
    bad_code = """
import subprocess

def run_backup(path):
    subprocess.run(f"tar -czf backup.tar.gz {path}", shell=True)
"""
    sanitizer = CommandInjectionSanitizer()
    findings = sanitizer.analyze(bad_code)
    assert len(findings) == 1
    assert "shell=True" in findings[0].vulnerable_call


def test_command_injection_synthesizes_safe_subprocess_and_imports():
    bad_code = """
import os

def check_disk(drive):
    os.system(drive)
"""
    healed, findings = sanitize_command_injection(bad_code)
    assert len(findings) == 1
    assert "subprocess.run(shlex.split(drive)" in healed
    assert "shell=False" in healed
    assert "import shlex" in healed
    assert "import subprocess" in healed

    # Verify synthesized code is syntactically valid and compiles
    compile(healed, "<test>", "exec")


def test_command_injection_transforms_shell_true_to_false_with_shlex():
    bad_code = """
import subprocess

def exec_cmd(user_arg):
    subprocess.run("ls " + user_arg, shell=True, check=True)
"""
    healed, findings = sanitize_command_injection(bad_code)
    assert len(findings) == 1
    assert "shell=False" in healed
    assert "shlex.split" in healed
    assert "import shlex" in healed
    compile(healed, "<test>", "exec")


def test_command_injection_clean_code_remains_unchanged():
    clean_code = """
import subprocess

def safe_ls(dir_path):
    subprocess.run(["ls", "-la", dir_path], shell=False, check=True)
"""
    sanitizer = CommandInjectionSanitizer()
    findings = sanitizer.analyze(clean_code)
    assert len(findings) == 0

    healed, findings = sanitize_command_injection(clean_code)
    assert len(findings) == 0
    assert healed == clean_code
