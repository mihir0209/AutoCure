"""
Notification Service - Demo Microservice (NOT equipped with AutoCure)
Port: 9003  |  Suggested User ID: notification-svc

A small notification / email-dispatch API that intentionally produces
errors at random intervals.  This service does NOT include the AutoCure
integration yet.  See the "Integration" section below for how to add it.

Errors injected:
  - ConnectionRefusedError  simulating SMTP failure
  - KeyError                missing template name
  - ValueError              invalid email address
  - TimeoutError            webhook delivery timeout

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

logger = logging.getLogger("notification")
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler(sys.stdout))

## ---------- AUTOCURE INTEGRATION (uncomment to enable) ---------- ###

import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from autocure_client import AutoCureHandler

AUTOCURE_WS = os.getenv("AUTOCURE_WS",
                         "ws://localhost:8000/ws/logs/notification-svc")
_autocure = AutoCureHandler(ws_url=AUTOCURE_WS, level=logging.DEBUG)
_autocure.setFormatter(logging.Formatter("%(name)s - %(message)s"))
logger.addHandler(_autocure)

## ---------------------------------------------------------------- ###

# ─── In-memory data ───────────────────────────────────────────────

templates = {
    "welcome": "Welcome to {app}, {name}!",
    "password_reset": "Reset your password: {link}",
    "order_confirm": "Order #{order_id} confirmed. Total: ${total}",
    # "invoice" deliberately missing
}

notification_log: list[dict] = []
notif_counter = 0


# ─── Error-injection helpers ──────────────────────────────────────

def _maybe_smtp_failure():
    """ConnectionRefusedError - SMTP server down."""
    if random.random() < 0.5:
        raise ConnectionRefusedError(
            "[Errno 111] SMTP connection refused: mail.internal.local:587"
        )
    return True


def _maybe_template_missing():
    """KeyError - missing notification template."""
    tpl_name = random.choice(["welcome", "order_confirm", "invoice", "password_reset"])
    body = templates[tpl_name]  # KeyError on "invoice"
    return body


def _maybe_bad_email():
    """ValueError - invalid email address."""
    addr = random.choice(["user@example.com", "not-an-email", "admin@corp.io"])
    if "@" not in addr:
        raise ValueError(f"Invalid email address: '{addr}'")
    return addr


def _maybe_webhook_timeout():
    """TimeoutError - webhook delivery."""
    if random.random() < 0.5:
        raise TimeoutError(
            "Webhook delivery to https://hooks.slack.com/T012/B345 timed out after 10s"
        )
    return True


ERROR_FUNCS = [_maybe_smtp_failure, _maybe_template_missing, _maybe_bad_email, _maybe_webhook_timeout]


async def _error_injector():
    """Background task that triggers random errors at intervals."""
    await asyncio.sleep(10)
    logger.info("Error injector started (interval 15-20s)")
    while True:
        delay = random.randint(15, 20)
        await asyncio.sleep(delay)
        fn = random.choice(ERROR_FUNCS)
        try:
            logger.info(f"Dispatching scheduled notification: {fn.__name__}")
            fn()
            logger.info("Notification dispatched successfully")
        except Exception:
            logger.error(
                f"Notification dispatch failed in {fn.__name__}",
                exc_info=True,
                extra={"api_endpoint": "/api/notifications", "http_method": "POST"},
            )


# ─── FastAPI Application ──────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Notification Service starting on port 9003")
    # ### AUTOCURE INTEGRATION (uncomment to enable) ###
    # _autocure.start_background()
    # logger.info(f"AutoCure WebSocket: {AUTOCURE_WS}")
    task = asyncio.create_task(_error_injector())
    yield
    task.cancel()
    logger.info("Notification Service shutting down")


app = FastAPI(title="Notification Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"service": "notification", "status": "healthy"}


@app.post("/api/notifications/email")
async def send_email(body: dict):
    global notif_counter
    to = body.get("to", "")
    template = body.get("template", "welcome")
    params = body.get("params", {})

    logger.info(f"Sending email: to={to}, template={template}")

    if "@" not in to:
        logger.error(
            f"Invalid email address: '{to}'",
            extra={"api_endpoint": "/api/notifications/email", "http_method": "POST"},
        )
        raise HTTPException(status_code=400, detail="Invalid email address")

    if template not in templates:
        logger.error(
            f"Template '{template}' not found - KeyError in templates dict",
            exc_info=True,
            extra={"api_endpoint": "/api/notifications/email", "http_method": "POST"},
        )
        raise HTTPException(status_code=404, detail=f"Template '{template}' not found")

    body_text = templates[template].format(**params) if params else templates[template]
    notif_counter += 1
    record = {
        "id": notif_counter,
        "type": "email",
        "to": to,
        "body": body_text,
        "status": "sent",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    notification_log.append(record)
    logger.info(f"Email #{notif_counter} sent to {to}")
    return record


@app.post("/api/notifications/webhook")
async def send_webhook(body: dict):
    global notif_counter
    url = body.get("url", "")
    payload = body.get("payload", {})

    logger.info(f"Sending webhook to {url}")

    if not url.startswith("http"):
        logger.error(
            f"Invalid webhook URL: '{url}'",
            extra={"api_endpoint": "/api/notifications/webhook", "http_method": "POST"},
        )
        raise HTTPException(status_code=400, detail="Invalid URL")

    # Simulate occasional timeout
    if random.random() < 0.15:
        logger.error(
            f"Webhook delivery to {url} timed out after 10s",
            exc_info=False,
            extra={"api_endpoint": "/api/notifications/webhook", "http_method": "POST"},
        )
        raise HTTPException(status_code=504, detail="Webhook delivery timeout")

    notif_counter += 1
    record = {
        "id": notif_counter,
        "type": "webhook",
        "url": url,
        "status": "delivered",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    notification_log.append(record)
    logger.info(f"Webhook #{notif_counter} delivered to {url}")
    return record


@app.get("/api/notifications")
async def list_notifications(limit: int = 20):
    logger.info("Listing recent notifications")
    return {"notifications": notification_log[-limit:]}


@app.get("/api/templates")
async def list_templates():
    return {"templates": list(templates.keys())}


# ─── Entry point ──────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("notification_service:app", host="0.0.0.0", port=9003, reload=False)
