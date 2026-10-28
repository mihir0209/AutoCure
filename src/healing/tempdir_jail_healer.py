"""
AutoCure Insecure Tempfile/Directory Jail Healer.
Enforces usage of tempfile.TemporaryDirectory with strict directory permissions.
"""
import tempfile
import os

def create_isolated_tempdir(prefix: str = "autocure_safe_") -> str:
    temp_dir = tempfile.mkdtemp(prefix=prefix)
    os.chmod(temp_dir, 0o700)
    return temp_dir
