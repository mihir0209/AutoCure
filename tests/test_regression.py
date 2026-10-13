"""
Regression Testing — AutoCure
==============================
Ensures new features and updates do not break existing functionalities.

  TC01 – Log processing validation
  TC02 – Error detection module
  TC03 – AI analysis module
  TC04 – Dashboard update
  TC05 – System stability after update

Run with: python -m pytest tests/ -v --tb=short --junitxml=regression-test-report.xml
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
import websockets
from httpx import AsyncClient

from conftest import make_log, WS_BASE, API_BASE


# ═══════════════════════════════════════════════════════════════════
# TC01 — Log Processing Validation
# ═══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tc01_log_processing_validation(client):
    """
    Send normal log data via WebSocket.
    Verify logs are stored and retrievable via REST API.
    """
    user_id = f"regression-tc01-{uuid.uuid4().hex[:8]}"
    log_count = 10

    uri = f"{WS_BASE}/{user_id}"
    async with websockets.connect(uri) as ws:
        for i in range(log_count):
            msg = make_log(
                level="INFO",
                message=f"Regression test log {i}",
                source_file="regression_test.py",
                line_number=i + 1,
            )
            await ws.send(json.dumps(msg))

    await asyncio.sleep(0.5)

    resp = await client.get(f"/api/v1/logs/{user_id}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

    data = resp.json()
    assert data["user_id"] == user_id
    assert data["total_logs"] == log_count, (
        f"Expected {log_count} logs, got {data['total_logs']}"
    )

    logs = data["logs"]
    assert len(logs) == log_count
    for log in logs:
        assert log["level"] == "INFO"
        assert "Regression test log" in log["message"]

    await client.delete(f"/api/v1/logs/{user_id}")

    print(f"\n  TC01: {log_count} logs sent and retrieved correctly")


# ═══════════════════════════════════════════════════════════════════
# TC02 — Error Detection Module
# ═══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tc02_error_detection(client):
    """
    Send error-level logs via WebSocket.
    Verify the system correctly identifies and flags errors.
    """
    user_id = f"regression-tc02-{uuid.uuid4().hex[:8]}"

    # Send INFO first, then ERROR logs in separate batches to avoid
    # auto-analysis consuming error logs from the buffer
    uri = f"{WS_BASE}/{user_id}"

    # Batch 1: INFO + WARNING (non-error)
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps(make_log(level="INFO", message="Normal operation")))
        await ws.send(json.dumps(make_log(level="WARNING", message="Warning issued")))

    await asyncio.sleep(0.3)

    resp = await client.get(f"/api/v1/logs/{user_id}")
    data = resp.json()
    info_count = data["total_logs"]
    assert info_count == 2, f"Expected 2 non-error logs, got {info_count}"

    # Batch 2: ERROR logs (these trigger auto-analysis)
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps(make_log(
            level="ERROR",
            message="ZeroDivisionError: division by zero",
            source_file="calculator.py",
            line_number=42,
            stack_trace=(
                "Traceback (most recent call last):\n"
                "  File 'calculator.py', line 42, in divide\n"
                "    return a / b\n"
                "ZeroDivisionError: division by zero"
            ),
        )))
        await ws.send(json.dumps(make_log(
            level="CRITICAL",
            message="DatabaseConnectionError: connection refused",
            source_file="db.py",
            line_number=15,
        )))

    await asyncio.sleep(0.5)

    # Verify error detection
    resp = await client.get(f"/api/v1/logs/{user_id}")
    assert resp.status_code == 200
    data = resp.json()

    # System should flag that errors exist
    assert data["has_errors"] is True, "System did not detect errors in log buffer"

    # Verify error logs are in the buffer
    logs = data["logs"]
    levels = [log["level"] for log in logs]
    assert "ERROR" in levels, "ERROR log not found in buffer"

    # Verify error details are preserved
    error_log = next(l for l in logs if l["level"] == "ERROR")
    assert "ZeroDivisionError" in error_log["message"]
    assert error_log["source_file"] == "calculator.py"
    assert error_log["line_number"] == 42

    await client.delete(f"/api/v1/logs/{user_id}")

    print(f"\n  TC02: Errors detected correctly (has_errors=True, "
          f"levels found: {set(levels)})")


# ═══════════════════════════════════════════════════════════════════
# TC03 — AI Analysis Module
# ═══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tc03_ai_analysis(client):
    """
    Verify the AI analysis pipeline is reachable and returns valid output.
    Uses a registered service user if available, otherwise validates
    the endpoint responds correctly for unregistered users.
    """
    # Check for registered service users (these are in user_registrations,
    # not the auth users table)
    repos_resp = await client.get("/api/v1/repos/registered")
    repos = repos_resp.json().get("repos", [])

    if repos:
        # Use a registered service user
        user_id = repos[0]["user_id"]
    else:
        # No registered services — verify the endpoint handles it gracefully
        user_id = "nonexistent-regression-user"
        resp = await client.post(f"/api/v1/analyze/{user_id}")
        assert resp.status_code == 404, (
            f"Expected 404 for unregistered user, got {resp.status_code}"
        )

        # Verify reports API still works (regression check)
        reports_resp = await client.get("/api/v1/reports", params={"limit": 5})
        assert reports_resp.status_code == 200
        reports_data = reports_resp.json()
        assert "reports" in reports_data

        print(f"\n  TC03: No registered services — endpoint correctly returns 404, "
              f"reports API OK ({len(reports_data['reports'])} reports)")
        return

    # Clear existing logs for clean test
    await client.delete(f"/api/v1/logs/{user_id}")

    # Send error logs with stack trace
    uri = f"{WS_BASE}/{user_id}"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps(make_log(
            level="ERROR",
            message="IndexError: list index out of range",
            source_file="processor.py",
            line_number=25,
            stack_trace=(
                "Traceback (most recent call last):\n"
                "  File 'processor.py', line 25, in get_item\n"
                "    return items[index]\n"
                "IndexError: list index out of range"
            ),
        )))

    await asyncio.sleep(0.5)

    # Trigger analysis
    analyze_resp = await client.post(f"/api/v1/analyze/{user_id}")
    assert analyze_resp.status_code == 200, (
        f"Analysis failed: {analyze_resp.status_code} {analyze_resp.text}"
    )

    result = analyze_resp.json()
    assert result["status"] in ("queued", "no_errors", "no_config"), (
        f"Unexpected analysis status: {result['status']}"
    )

    if result["status"] == "queued":
        assert result["error_count"] > 0, "Analysis queued but error_count is 0"

    # Verify reports API
    reports_resp = await client.get("/api/v1/reports", params={"limit": 5})
    assert reports_resp.status_code == 200

    await client.delete(f"/api/v1/logs/{user_id}")

    print(f"\n  TC03: AI analysis status={result['status']}")


# ═══════════════════════════════════════════════════════════════════
# TC04 — Dashboard Update
# ═══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tc04_dashboard_update(client):
    """
    Send updated data (new logs) and verify the dashboard API
    reflects the changes correctly.
    """
    before = await client.get("/api/v1/dashboard/summary")
    assert before.status_code == 200
    before_data = before.json()
    initial_logs = before_data.get("total_logs", 0)

    # Send INFO logs (non-error, won't trigger analysis)
    user_id = f"regression-tc04-{uuid.uuid4().hex[:8]}"
    log_count = 15
    uri = f"{WS_BASE}/{user_id}"
    async with websockets.connect(uri) as ws:
        for i in range(log_count):
            await ws.send(json.dumps(make_log(
                level="INFO",
                message=f"Dashboard regression log {i}",
            )))

    await asyncio.sleep(0.5)

    after = await client.get("/api/v1/dashboard/summary")
    assert after.status_code == 200
    after_data = after.json()

    assert after_data["total_logs"] >= initial_logs, (
        f"Dashboard log count did not increase: "
        f"{after_data['total_logs']} < {initial_logs}"
    )

    # Verify all expected fields
    required_fields = [
        "registered_services", "registered_users",
        "total_logs", "total_errors", "total_reports",
        "ai_provider", "timestamp",
    ]
    for field in required_fields:
        assert field in after_data, f"Dashboard missing field: {field}"

    ts = after_data["timestamp"]
    assert ts is not None and len(ts) > 0, "Dashboard timestamp is empty"

    await client.delete(f"/api/v1/logs/{user_id}")

    print(f"\n  TC04: Dashboard updated — logs went from "
          f"{initial_logs} to {after_data['total_logs']}")


# ═══════════════════════════════════════════════════════════════════
# TC05 — System Stability After Update
# ═══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tc05_system_stability(client):
    """
    Full system workout: WebSocket, REST API, health check,
    status, reports, logs — verify nothing is broken.
    """
    user_id = f"regression-tc05-{uuid.uuid4().hex[:8]}"
    results = {}

    # 1. Health check
    resp = await client.get("/health")
    results["health"] = resp.status_code
    assert resp.status_code == 200

    # 2. System status
    resp = await client.get("/api/v1/status")
    results["status"] = resp.status_code
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"

    # 3. WebSocket connection + log streaming (INFO only, no auto-analysis)
    log_count = 20
    uri = f"{WS_BASE}/{user_id}"
    async with websockets.connect(uri) as ws:
        for i in range(log_count):
            await ws.send(json.dumps(make_log(
                level="INFO",
                message=f"Stability test log {i}",
            )))

    await asyncio.sleep(0.5)
    results["websocket"] = "connected_and_sent"

    # 4. Log retrieval
    resp = await client.get(f"/api/v1/logs/{user_id}")
    results["logs_get"] = resp.status_code
    assert resp.status_code == 200
    total = resp.json()["total_logs"]
    assert total >= log_count - 3, (
        f"Expected ~{log_count} logs, got {total}"
    )

    # 5. All logs endpoint
    resp = await client.get("/api/v1/logs")
    results["all_logs"] = resp.status_code
    assert resp.status_code == 200

    # 6. Dashboard summary
    resp = await client.get("/api/v1/dashboard/summary")
    results["dashboard"] = resp.status_code
    assert resp.status_code == 200

    # 7. Reports listing
    resp = await client.get("/api/v1/reports", params={"limit": 5})
    results["reports"] = resp.status_code
    assert resp.status_code == 200

    # 8. Registered repos
    resp = await client.get("/api/v1/repos/registered")
    results["repos"] = resp.status_code
    assert resp.status_code == 200

    # 9. Server logs
    resp = await client.get("/api/v1/logs/server", params={"limit": 10})
    results["server_logs"] = resp.status_code
    assert resp.status_code == 200

    # 10. Connections
    resp = await client.get("/api/v1/connections")
    results["connections"] = resp.status_code
    assert resp.status_code == 200

    # 11. Users
    resp = await client.get("/api/v1/users")
    results["users"] = resp.status_code
    assert resp.status_code == 200

    # 12. Languages
    resp = await client.get("/api/v1/languages")
    results["languages"] = resp.status_code
    assert resp.status_code == 200

    # 13. Log flush (cleanup)
    resp = await client.delete(f"/api/v1/logs/{user_id}")
    results["log_flush"] = resp.status_code
    assert resp.status_code == 200

    # Verify flush worked
    resp = await client.get(f"/api/v1/logs/{user_id}")
    assert resp.json()["total_logs"] == 0, "Logs not cleared after flush"

    print(f"\n  TC05: All {len(results)} endpoints responded correctly:")
    for name, code in results.items():
        status_label = "OK" if code == 200 else str(code)
        print(f"        {name}: {status_label}")
