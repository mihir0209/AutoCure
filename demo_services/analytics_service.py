"""
Analytics Service - Demo Microservice (NOT equipped with AutoCure)
Port: 9004  |  Suggested User ID: analytics-svc

A small analytics / metrics API that intentionally produces errors at
random intervals.  This service does NOT include the AutoCure
integration yet.  See the "Integration" section below for how to add it.

Errors injected:
  - ZeroDivisionError  computing averages on empty dataset
  - AttributeError     accessing a None metric object
  - OverflowError      when counter exceeds simulated limit
  - FileNotFoundError  when reading a CSV export that doesn't exist

=======================================================================
  INTEGRATION INSTRUCTIONS  (to connect this service to AutoCure)
=======================================================================
1.  Copy  autocure_client.py  into this directory  (already present in
    the demo_services/ folder).
2.  Uncomment the block marked  "### AUTOCURE INTEGRATION ###"  below.
3.  That's it!  The handler attaches to Python's logging module and
    streams every WARNING+ log to AutoCure over WebSocket.
=======================================================================
"""

import asyncio
import logging
import random
import sys
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
import uvicorn

logger = logging.getLogger("analytics")
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler(sys.stdout))

### ---------- AUTOCURE INTEGRATION (uncomment to enable) ---------- ###
#
# import os
# from pathlib import Path
# sys.path.insert(0, str(Path(__file__).parent))
# from autocure_client import AutoCureHandler
#
# AUTOCURE_WS = os.getenv("AUTOCURE_WS",
#                          "ws://localhost:8000/ws/logs/analytics-svc")
# _autocure = AutoCureHandler(ws_url=AUTOCURE_WS, level=logging.DEBUG)
# _autocure.setFormatter(logging.Formatter("%(name)s - %(message)s"))
# logger.addHandler(_autocure)
#
### ---------------------------------------------------------------- ###

# ─── In-memory data ───────────────────────────────────────────────

events: list[dict] = []
metrics: dict = {
    "page_views": {"count": 0, "last_value": None},
    "signups": {"count": 0, "last_value": None},
    "api_calls": {"count": 0, "last_value": None},
    # "conversions" deliberately missing to trigger KeyError
}

COUNTER_LIMIT = 999_999
event_counter = 0


# ─── Error-injection helpers ──────────────────────────────────────

def _maybe_div_zero():
    """ZeroDivisionError computing average on empty dataset."""
    empty_dataset: list[float] = []
    avg = sum(empty_dataset) / len(empty_dataset)  # ZeroDivisionError
    return avg


def _maybe_attr_error():
    """AttributeError on None metric."""
    metric = metrics.get("conversions")  # returns None
    return metric["count"]  # TypeError: 'NoneType' is not subscriptable


def _maybe_overflow():
    """OverflowError when counter exceeds limit."""
    val = COUNTER_LIMIT + random.randint(1, 100)
    if val > COUNTER_LIMIT:
        raise OverflowError(
            f"Metric counter overflow: {val} exceeds limit {COUNTER_LIMIT}"
        )
    return val


def _maybe_file_not_found():
    """FileNotFoundError reading missing export."""
    path = f"/tmp/analytics_export_{random.randint(1000,9999)}.csv"
    with open(path, "r") as f:  # FileNotFoundError
        return f.read()


ERROR_FUNCS = [_maybe_div_zero, _maybe_attr_error, _maybe_overflow, _maybe_file_not_found]


async def _error_injector():
    """Background task that triggers random errors at intervals."""
    await asyncio.sleep(12)
    logger.info("Error injector started (interval 55-110s)")
    while True:
        delay = random.randint(55, 110)
        await asyncio.sleep(delay)
        fn = random.choice(ERROR_FUNCS)
        try:
            logger.info(f"Running analytics pipeline: {fn.__name__}")
            fn()
            logger.info("Analytics pipeline step completed")
        except Exception:
            logger.error(
                f"Analytics pipeline failed in {fn.__name__}",
                exc_info=True,
                extra={"api_endpoint": "/api/analytics", "http_method": "GET"},
            )


# ─── FastAPI Application ──────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Analytics Service starting on port 9004")
    # ### AUTOCURE INTEGRATION (uncomment to enable) ###
    # _autocure.start_background()
    # logger.info(f"AutoCure WebSocket: {AUTOCURE_WS}")
    task = asyncio.create_task(_error_injector())
    yield
    task.cancel()
    logger.info("Analytics Service shutting down")


app = FastAPI(title="Analytics Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"service": "analytics", "status": "healthy"}


@app.post("/api/events")
async def track_event(body: dict):
    global event_counter
    event_type = body.get("event", "page_view")
    user_id = body.get("user_id", "anonymous")
    properties = body.get("properties", {})

    logger.info(f"Tracking event: {event_type} by {user_id}")

    event_counter += 1
    record = {
        "id": event_counter,
        "event": event_type,
        "user_id": user_id,
        "properties": properties,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    events.append(record)

    # Update metric counters
    metric_key = event_type.replace(" ", "_").lower()
    if metric_key in metrics:
        metrics[metric_key]["count"] += 1
        metrics[metric_key]["last_value"] = datetime.now(timezone.utc).isoformat()

    return record


@app.get("/api/events")
async def list_events(limit: int = 50):
    logger.info(f"Listing last {limit} events")
    return {"events": events[-limit:], "total": len(events)}


@app.get("/api/metrics")
async def get_metrics():
    logger.info("Fetching all metrics")
    return {"metrics": metrics, "total_events": len(events)}


@app.get("/api/metrics/{key}")
async def get_metric(key: str):
    logger.info(f"Fetching metric: {key}")
    if key not in metrics:
        logger.error(
            f"Metric '{key}' not found - available: {list(metrics.keys())}",
            extra={"api_endpoint": f"/api/metrics/{key}", "http_method": "GET"},
        )
        raise HTTPException(status_code=404, detail=f"Metric '{key}' not found")
    return {key: metrics[key]}


@app.get("/api/analytics/summary")
async def analytics_summary():
    """Summary that can trigger ZeroDivisionError."""
    logger.info("Computing analytics summary")
    try:
        if not events:
            logger.warning("No events recorded yet - empty dataset")
            return {"total_events": 0, "avg_per_hour": 0}
        total = len(events)
        # Deliberately fragile: hours_elapsed can be 0
        first_ts = events[0].get("timestamp", "")
        hours_elapsed = 0  # BUG: should compute actual elapsed hours
        avg = total / hours_elapsed if hours_elapsed else total
        return {"total_events": total, "avg_per_hour": round(avg, 2)}
    except ZeroDivisionError:
        logger.error(
            "ZeroDivisionError in analytics summary: hours_elapsed is 0",
            exc_info=True,
            extra={"api_endpoint": "/api/analytics/summary", "http_method": "GET"},
        )
        raise HTTPException(status_code=500, detail="Analytics computation error")


@app.get("/api/export")
async def export_data(format: str = "json"):
    """Export that can trigger FileNotFoundError."""
    logger.info(f"Exporting analytics data as {format}")
    if format == "json":
        return {"events": events, "metrics": metrics}
    elif format == "csv":
        csv_path = "/tmp/analytics_export.csv"
        try:
            with open(csv_path, "r") as f:
                return {"csv": f.read()}
        except FileNotFoundError:
            logger.error(
                f"Export file not found: {csv_path}",
                exc_info=True,
                extra={"api_endpoint": "/api/export", "http_method": "GET"},
            )
            raise HTTPException(status_code=500, detail="Export file not available")
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")


# ─── Entry point ──────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("analytics_service:app", host="0.0.0.0", port=9004, reload=False)
