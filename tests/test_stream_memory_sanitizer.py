"""Unit and Regression Tests for Stream Memory Exhaustion Sanitizer."""

import io
import pytest
from healing.stream_memory_sanitizer import (
    StreamMemoryFinding,
    StreamMemorySanitizer,
    sanitize_stream_memory,
)


def test_stream_memory_detects_unbounded_read():
    unsafe_code = """
def process_upload(f):
    content = f.read()
    return content
"""
    engine = StreamMemorySanitizer()
    findings = engine.analyze(unsafe_code)
    assert len(findings) == 1
    assert findings[0].method_name == "read"
    assert "OOM exhaustion" in findings[0].vulnerability_reason


def test_stream_memory_synthesizes_bounded_read():
    unsafe_code = """
def read_payload(stream):
    return stream.read()
"""
    healed, findings = sanitize_stream_memory(unsafe_code)
    assert len(findings) == 1
    assert "stream.read(65536)" in healed

    # Verify execution
    compiled = compile(healed, "<test>", "exec")
    namespace = {}
    exec(compiled, namespace)
    fake_stream = io.BytesIO(b"Hello world" * 10)
    res = namespace["read_payload"](fake_stream)
    assert res == b"Hello world" * 10


def test_stream_memory_preserves_bounded_read():
    safe_code = """
def read_header(f):
    return f.read(1024)
"""
    healed, findings = sanitize_stream_memory(safe_code)
    assert len(findings) == 0
    assert healed.strip() == safe_code.strip()
