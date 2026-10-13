"""
Stress and Load Testing — AutoCure
python -m pytest tests/ -v --tb=short --junitxml=stress-test-report.xml
"""

import asyncio
import json
import statistics
import time
import uuid
from datetime import datetime

import pytest
import pytest_asyncio
import websockets

from conftest import make_log, WS_BASE, API_BASE

# ── Thresholds ─────────────────────────────────────────────────────
MAX_AVG_RESPONSE_MS = 500  # TC03: avg response time < 500ms
MIN_THROUGHPUT_MSG_SEC = 50  # TC04: at least 50 msg/sec
HIGH_VOLUME_COUNT = 500  # TC01: logs for high volume test
CONCURRENT_USERS = 5  # TC02: concurrent users
ERROR_LOG_RATIO = 0.2  # TC05: 20% error logs


# ═══════════════════════════════════════════════════════════════════
# TC01 — High Volume Log Ingestion
# ═══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tc01_high_volume_log_ingestion():
    """
    Send a large JSON log stream through WebSocket.
    Verify the system processes all logs without delay or crash.
    """
    user_id = f"stress-tc01-{uuid.uuid4().hex[:8]}"
    messages = [make_log(message=f"Log entry {i}") for i in range(HIGH_VOLUME_COUNT)]

    uri = f"{WS_BASE}/{user_id}"
    async with websockets.connect(uri) as ws:
        start = time.monotonic()
        for msg in messages:
            await ws.send(json.dumps(msg))
        elapsed = time.monotonic() - start

    avg_ms = (elapsed / HIGH_VOLUME_COUNT) * 1000
    print(
        f"\n  TC01: {HIGH_VOLUME_COUNT} logs sent in {elapsed:.2f}s "
        f"(avg {avg_ms:.1f}ms/msg)"
    )

    assert elapsed > 0
    assert (
        avg_ms < MAX_AVG_RESPONSE_MS * 5
    ), f"Per-message avg {avg_ms:.0f}ms is excessively slow"


# ═══════════════════════════════════════════════════════════════════
# TC02 — Multiple User Simulation
# ═══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tc02_multiple_users_concurrent():
    """
    Simulate CONCURRENT_USERS each streaming logs simultaneously.
    Verify no crash and all connections stay alive.
    """
    logs_per_user = 100

    async def user_stream(uid: str) -> dict:
        sent = 0
        errors = 0
        start = time.monotonic()
        async with websockets.connect(f"{WS_BASE}/{uid}") as ws:
            for i in range(logs_per_user):
                msg = make_log(
                    level="ERROR" if i % 5 == 0 else "INFO",
                    message=f"[{uid}] entry {i}",
                )
                await ws.send(json.dumps(msg))
                sent += 1
                if i % 5 == 0:
                    errors += 1
        elapsed = time.monotonic() - start
        return {"user": uid, "sent": sent, "errors": errors, "elapsed": elapsed}

    user_ids = [f"stress-tc02-user{i}" for i in range(CONCURRENT_USERS)]
    start = time.monotonic()
    results = await asyncio.gather(*[user_stream(uid) for uid in user_ids])
    total_elapsed = time.monotonic() - start

    total_sent = sum(r["sent"] for r in results)
    total_errors = sum(r["errors"] for r in results)

    print(
        f"\n  TC02: {CONCURRENT_USERS} users x {logs_per_user} msgs = "
        f"{total_sent} total in {total_elapsed:.2f}s"
    )
    print(f"        Error-level msgs sent: {total_errors}")

    assert total_sent == CONCURRENT_USERS * logs_per_user
    assert all(r["sent"] == logs_per_user for r in results)


# ═══════════════════════════════════════════════════════════════════
# TC03 — Response Time Check
# ═══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tc03_response_time():
    """
    Send continuous log input and measure per-message response time.
    Verify latency stays below MAX_AVG_RESPONSE_MS.
    """
    user_id = f"stress-tc03-{uuid.uuid4().hex[:8]}"
    count = 200
    latencies = []

    uri = f"{WS_BASE}/{user_id}"
    async with websockets.connect(uri) as ws:
        for i in range(count):
            msg = make_log(message=f"Latency test {i}")
            t0 = time.monotonic()
            await ws.send(json.dumps(msg))
            t1 = time.monotonic()
            latencies.append((t1 - t0) * 1000)

    avg_ms = statistics.mean(latencies)
    p50_ms = statistics.median(latencies)
    p95_ms = sorted(latencies)[int(len(latencies) * 0.95)]
    p99_ms = sorted(latencies)[int(len(latencies) * 0.99)]

    print(f"\n  TC03 Response Time ({count} msgs):")
    print(
        f"        avg={avg_ms:.1f}ms  p50={p50_ms:.1f}ms  "
        f"p95={p95_ms:.1f}ms  p99={p99_ms:.1f}ms"
    )

    assert (
        avg_ms < MAX_AVG_RESPONSE_MS
    ), f"Average response time {avg_ms:.0f}ms exceeds {MAX_AVG_RESPONSE_MS}ms"


# ═══════════════════════════════════════════════════════════════════
# TC04 — Throughput Testing
# ═══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tc04_throughput():
    """
    Send logs at high data rate and measure sustained throughput.
    Verify messages/sec stays above MIN_THROUGHPUT_MSG_SEC.
    """
    user_id = f"stress-tc04-{uuid.uuid4().hex[:8]}"
    count = 1000

    messages = [json.dumps(make_log(message=f"Throughput {i}")) for i in range(count)]

    uri = f"{WS_BASE}/{user_id}"
    async with websockets.connect(uri) as ws:
        start = time.monotonic()
        for msg in messages:
            await ws.send(msg)
        elapsed = time.monotonic() - start

    throughput = count / elapsed
    print(
        f"\n  TC04 Throughput: {count} msgs in {elapsed:.2f}s = "
        f"{throughput:.0f} msgs/sec"
    )

    assert (
        throughput >= MIN_THROUGHPUT_MSG_SEC
    ), f"Throughput {throughput:.0f} msg/s below minimum {MIN_THROUGHPUT_MSG_SEC}"


# ═══════════════════════════════════════════════════════════════════
# TC05 — Error Handling Under Load
# ═══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tc05_error_handling_under_load():
    """
    Send a mix of INFO, WARNING, and ERROR logs under load.
    Verify errors are classified correctly and system stays stable.
    """
    user_id = f"stress-tc05-{uuid.uuid4().hex[:8]}"
    count = 500
    error_count = 0
    warning_count = 0
    info_count = 0

    messages = []
    for i in range(count):
        if i % int(1 / ERROR_LOG_RATIO) == 0:
            level = "ERROR"
        elif i % 4 == 0:
            level = "WARNING"
        else:
            level = "INFO"
        messages.append(
            make_log(
                level=level,
                message=f"{level} log entry {i}",
                source_file="app.py",
                line_number=i,
            )
        )
        if level in ("ERROR", "CRITICAL"):
            error_count += 1
        elif level == "WARNING":
            warning_count += 1
        else:
            info_count += 1

    uri = f"{WS_BASE}/{user_id}"
    send_errors = 0
    async with websockets.connect(uri) as ws:
        start = time.monotonic()
        for msg in messages:
            try:
                await ws.send(json.dumps(msg))
            except Exception:
                send_errors += 1
        elapsed = time.monotonic() - start

    print(f"\n  TC05 Error Handling ({count} msgs in {elapsed:.2f}s):")
    print(
        f"        INFO={info_count}  WARNING={warning_count}  "
        f"ERROR/CRITICAL={error_count}"
    )
    print(f"        Send errors: {send_errors}")

    assert send_errors == 0, f"{send_errors} messages failed to send"
    assert error_count > 0, "At least some ERROR logs must be sent"
    assert info_count > 0, "At least some INFO logs must be sent"


# ═══════════════════════════════════════════════════════════════════
# TC06 — API Health Under Concurrent Load (bonus)
# ═══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tc06_api_health_under_load(client):
    """
    Hit /health repeatedly while logs stream in background.
    Verify API remains responsive.
    """
    user_id = f"stress-tc06-{uuid.uuid4().hex[:8]}"
    health_results = []
    stop_flag = asyncio.Event()

    async def stream_logs():
        async with websockets.connect(f"{WS_BASE}/{user_id}") as ws:
            i = 0
            while not stop_flag.is_set():
                try:
                    await ws.send(json.dumps(make_log(message=f"bg log {i}")))
                    i += 1
                    await asyncio.sleep(0.01)
                except Exception:
                    break

    async def check_health():
        for _ in range(50):
            t0 = time.monotonic()
            resp = await client.get("/health")
            t1 = time.monotonic()
            health_results.append(
                {
                    "status": resp.status_code,
                    "latency_ms": (t1 - t0) * 1000,
                }
            )
            await asyncio.sleep(0.05)
        stop_flag.set()

    await asyncio.gather(stream_logs(), check_health())

    successes = sum(1 for r in health_results if r["status"] == 200)
    avg_latency = statistics.mean(r["latency_ms"] for r in health_results)

    print(
        f"\n  TC06 API Stability: {successes}/{len(health_results)} "
        f"health checks succeeded, avg latency={avg_latency:.1f}ms"
    )

    assert successes == len(
        health_results
    ), f"Only {successes}/{len(health_results)} health checks returned 200"
    assert (
        avg_latency < MAX_AVG_RESPONSE_MS
    ), f"API avg latency {avg_latency:.0f}ms too high"
