"""Unit and Regression Tests for Path Traversal AST Sanitizer."""

import os
import pytest
from healing.path_traversal_sanitizer import (
    PathTraversalFinding,
    PathTraversalSanitizer,
    sanitize_path_traversal,
)


def test_path_traversal_detects_unsafe_os_path_join():
    unsafe_code = """
import os

def load_user_profile(user_filename: str):
    base_dir = "/var/data/uploads"
    full_path = os.path.join(base_dir, user_filename)
    return full_path
"""
    engine = PathTraversalSanitizer()
    findings = engine.analyze(unsafe_code)
    assert len(findings) == 1
    assert findings[0].call_name == "os.path.join"
    assert "user_filename" in findings[0].target_arg


def test_path_traversal_synthesizes_safe_basename():
    unsafe_code = """
import os

def load_file(user_input: str):
    return os.path.join("/base/path", user_input)
"""
    healed, findings = sanitize_path_traversal(unsafe_code)
    assert len(findings) == 1
    assert "os.path.basename(user_input)" in healed

    # Execute healed code to verify directory traversal is blocked
    compiled = compile(healed, "<test>", "exec")
    namespace = {}
    exec(compiled, namespace)
    res = namespace["load_file"]("../../../etc/passwd")
    # Result should be /base/path/passwd, NOT /etc/passwd
    assert res == "/base/path/passwd"


def test_path_traversal_ignores_constant_joins():
    safe_code = """
import os

def get_static_asset():
    return os.path.join("assets", "logo.png")
"""
    healed, findings = sanitize_path_traversal(safe_code)
    assert len(findings) == 0
    assert healed.strip() == safe_code.strip()
