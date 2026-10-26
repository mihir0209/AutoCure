import pytest
from healing.path_traversal_sanitizer import PathTraversalSanitizer, is_path_safe


def test_path_traversal_detects_concatenated_open():
    code = """
import os

def read_user_file(filename):
    with open("/var/www/uploads/" + filename, "r") as f:
        return f.read()
"""
    sanitizer = PathTraversalSanitizer()
    findings = sanitizer.analyze(code)
    assert len(findings) == 1
    assert "open()" in findings[0].vulnerable_operation


def test_path_traversal_detects_archive_extractall():
    code = """
import tarfile

def extract_package(archive_path):
    with tarfile.open(archive_path) as tar:
        tar.extractall("/tmp/extracted")
"""
    sanitizer = PathTraversalSanitizer()
    findings = sanitizer.analyze(code)
    assert len(findings) == 1
    assert "extractall" in findings[0].vulnerable_operation


def test_is_path_safe_blocks_directory_traversal():
    base = "/app/user_data"
    assert is_path_safe(base, "profile.json")
    assert is_path_safe(base, "nested/avatar.png")
    assert not is_path_safe(base, "../../../etc/passwd")
    assert not is_path_safe(base, "sub/../../../../root/.ssh/id_rsa")
