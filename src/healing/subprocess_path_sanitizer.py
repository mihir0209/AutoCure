"""
AutoCure Subprocess PATH Hijacking Sanitizer.
Ensures binary executables are resolved to absolute paths before invocation.
"""
import shutil
import os

def sanitize_executable_path(executable_name: str) -> str:
    if os.path.isabs(executable_name):
        return executable_name
    resolved = shutil.which(executable_name)
    if not resolved:
        raise FileNotFoundError(f"Executable '{executable_name}' not found on system PATH")
    return resolved
