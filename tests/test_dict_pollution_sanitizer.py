import pytest
from healing.dict_pollution_sanitizer import (
    DictPollutionSanitizer,
    safe_dict_merge,
)


def test_dict_pollution_detects_unsafe_merge_function():
    code = """
def deep_merge(dest, src):
    for k, v in src.items():
        if isinstance(v, dict):
            deep_merge(dest.setdefault(k, {}), v)
        else:
            dest[k] = v
    return dest
"""
    sanitizer = DictPollutionSanitizer()
    findings = sanitizer.analyze(code)
    assert len(findings) == 1
    assert findings[0].vulnerable_function == "deep_merge"


def test_safe_dict_merge_strips_forbidden_attributes():
    target = {"name": "guest", "settings": {"theme": "light"}}
    malicious_payload = {
        "__class__": {"admin": True},
        "__proto__": {"injected": "exploit"},
        "settings": {"theme": "dark", "__dict__": {"pwned": True}},
        "role": "user",
    }

    result = safe_dict_merge(target, malicious_payload)
    assert result["role"] == "user"
    assert result["settings"]["theme"] == "dark"
    assert "__class__" not in result
    assert "__proto__" not in result
    assert "__dict__" not in result["settings"]
