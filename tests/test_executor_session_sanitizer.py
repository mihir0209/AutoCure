"""Tests for Unclosed Network Session & ThreadPoolExecutor Sanitizer."""

import ast
import pytest
from healing.executor_session_sanitizer import (
    ExecutorSessionSanitizer,
    sanitize_executor_sessions,
)


def test_detects_and_wraps_bare_thread_pool_executor():
    code = """
def run_tasks(items):
    executor = ThreadPoolExecutor(max_workers=4)
    results = list(executor.map(process, items))
    return results
"""
    healed, findings = sanitize_executor_sessions(code)
    assert len(findings) == 1
    assert findings[0].resource_type == "ThreadPoolExecutor"
    assert findings[0].variable_name == "executor"

    assert "with ThreadPoolExecutor(max_workers=4) as executor:" in healed
    assert "results = list(executor.map(process, items))" in healed


def test_detects_and_wraps_requests_session():
    code = """
def query_api(url):
    session = requests.Session()
    response = session.get(url)
    return response.json()
"""
    healed, findings = sanitize_executor_sessions(code)
    assert len(findings) == 1
    assert findings[0].resource_type == "Session"
    assert "with requests.Session() as session:" in healed
    assert "response = session.get(url)" in healed


def test_ignores_already_managed_with_context():
    code = """
def clean_fetch(url):
    with requests.Session() as session:
        return session.get(url).text
"""
    healed, findings = sanitize_executor_sessions(code)
    assert len(findings) == 0
    assert ast.dump(ast.parse(healed)) == ast.dump(ast.parse(code))
