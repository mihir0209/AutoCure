"""Unit & Adversarial Tests for Async/Await Concurrency Deadlock Sanitizer."""

import asyncio
import pytest
from healing.async_deadlock_sanitizer import (
    AsyncDeadlockSanitizer,
    sanitize_async_deadlocks,
)


def test_rewrites_blocking_time_sleep_in_coroutine():
    source = """
import time

async def worker_job():
    time.sleep(0.01)
    return "done"
"""
    new_code, findings = sanitize_async_deadlocks(source)

    assert len(findings) == 1
    assert findings[0].call_name == "time.sleep"
    assert "await asyncio.sleep" in findings[0].remediation_applied

    assert "await asyncio.sleep(0.01)" in new_code
    assert "import asyncio" in new_code

    # Execute async code via event loop
    scope = {}
    exec(new_code, scope)
    worker = scope["worker_job"]
    res = asyncio.run(worker())
    assert res == "done"


def test_wraps_blocking_requests_in_to_thread():
    source = """
async def fetch_profile(url):
    resp = requests.get(url)
    return resp
"""
    new_code, findings = sanitize_async_deadlocks(source)

    assert len(findings) == 1
    assert findings[0].call_name == "requests.get"
    assert "await asyncio.to_thread(requests.get, url)" in new_code


def test_inserts_missing_await_on_coroutine_calls():
    source = """
async def helper_task():
    return 42

async def main_pipeline():
    res = helper_task()
    return res
"""
    new_code, findings = sanitize_async_deadlocks(source)

    assert len(findings) == 1
    assert findings[0].call_name == "helper_task"
    assert "res = await helper_task()" in new_code

    scope = {}
    exec(new_code, scope)
    pipeline = scope["main_pipeline"]
    res = asyncio.run(pipeline())
    assert res == 42


def test_leaves_synchronous_functions_untouched():
    source = """
import time

def sync_worker():
    time.sleep(1)
    return "sync_done"
"""
    new_code, findings = sanitize_async_deadlocks(source)

    assert len(findings) == 0
    assert "await" not in new_code
    assert "time.sleep(1)" in new_code
