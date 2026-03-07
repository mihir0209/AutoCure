"""
Payment Service - Demo Microservice (EQUIPPED with AutoCure)
Port: 9002  |  User ID: payment-svc

A small payment-processing API that intentionally produces errors at
random intervals to demonstrate the AutoCure self-healing platform.

Errors injected:
  - ValueError     when card number validation fails
  - KeyError       when currency code is missing
  - TypeError      when amount is wrong type
  - RuntimeError   when payment gateway "times out"
"""

import asyncio
import logging
import random
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
import uvicorn

# ─── AutoCure integration ──────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from autocure_client import AutoCureHandler

AUTOCURE_WS = os.getenv("AUTOCURE_WS", "ws://localhost:8000/ws/logs/payment-svc")

autocure = AutoCureHandler(ws_url=AUTOCURE_WS, level=logging.DEBUG)
autocure.setFormatter(logging.Formatter("%(name)s - %(message)s"))

logger = logging.getLogger("payment")
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler(sys.stdout))
logger.addHandler(autocure)

# ─── In-memory data ───────────────────────────────────────────────

exchange_rates = {
    "USD": 1.0,
    "EUR": 0.92,
    "GBP": 0.79,
    "JPY": 149.50,
    "INR": 83.12,
    # "CAD" deliberately missing to trigger KeyError
}

transactions: list[dict] = []
tx_counter = 0


# ─── Error-injection helpers ──────────────────────────────────────

def _maybe_value_error():
    """ValueError from card validation."""
    card = random.choice(["4111111111111111", "bad-card-number", "5500000000000004"])
    if not card.isdigit():
        raise ValueError(f"Invalid card number: '{card}' contains non-digit characters")
    return card


def _maybe_key_error():
    """KeyError for unsupported currency."""
    currency = random.choice(["USD", "EUR", "CAD", "GBP"])
    rate = exchange_rates[currency]  # KeyError on CAD
    return rate


def _maybe_type_error():
    """TypeError when amount is a string."""
    amount = random.choice([49.99, 125.0, "ninety-nine", 10.0])
    tax = amount * 0.08  # TypeError on string
    return tax


def _maybe_runtime_error():
    """RuntimeError simulating gateway timeout."""
    if random.random() < 0.6:
        raise RuntimeError("Payment gateway timeout after 30000ms - connection refused")
    return True


ERROR_FUNCS = [_maybe_value_error, _maybe_key_error, _maybe_type_error, _maybe_runtime_error]


async def _error_injector():
    """Background task that triggers random errors at intervals."""
    await asyncio.sleep(8)
    logger.info("Error injector started (interval 40-80s)")
    while True:
        delay = random.randint(40, 80)
        await asyncio.sleep(delay)
        fn = random.choice(ERROR_FUNCS)
        try:
            logger.info(f"Processing scheduled payment batch: {fn.__name__}")
            fn()
            logger.info("Payment batch processed successfully")
        except Exception:
            logger.error(
                f"Payment processing failed in {fn.__name__}",
                exc_info=True,
                extra={"api_endpoint": "/api/payments", "http_method": "POST"},
            )


# ─── FastAPI Application ──────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    autocure.start_background()
    logger.info("Payment Service starting on port 9002")
    logger.info(f"AutoCure WebSocket: {AUTOCURE_WS}")
    task = asyncio.create_task(_error_injector())
    yield
    task.cancel()
    logger.info("Payment Service shutting down")


app = FastAPI(title="Payment Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"service": "payment", "status": "healthy", "autocure": autocure.is_connected}


@app.post("/api/payments")
async def create_payment(body: dict):
    global tx_counter
    card = body.get("card_number", "")
    amount = body.get("amount", 0)
    currency = body.get("currency", "USD")

    logger.info(f"Payment request: amount={amount} {currency}")

    # Validate card
    if not card or not str(card).isdigit() or len(str(card)) < 13:
        logger.error(
            f"Invalid card number supplied: '{card}'",
            exc_info=False,
            extra={"api_endpoint": "/api/payments", "http_method": "POST"},
        )
        raise HTTPException(status_code=400, detail="Invalid card number")

    # Convert currency
    if currency not in exchange_rates:
        logger.error(
            f"Unsupported currency code: '{currency}' - KeyError in exchange_rates lookup",
            exc_info=True,
            extra={"api_endpoint": "/api/payments", "http_method": "POST"},
        )
        raise HTTPException(status_code=400, detail=f"Unsupported currency: {currency}")

    usd_amount = amount / exchange_rates[currency]
    tx_counter += 1
    tx = {
        "tx_id": tx_counter,
        "amount": amount,
        "currency": currency,
        "usd_equivalent": round(usd_amount, 2),
        "status": "completed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    transactions.append(tx)
    logger.info(f"Payment #{tx_counter} completed: ${usd_amount:.2f} USD")
    return tx


@app.get("/api/payments")
async def list_payments(limit: int = 20):
    logger.info("Listing recent payments")
    return {"transactions": transactions[-limit:]}


@app.post("/api/refund/{tx_id}")
async def refund_payment(tx_id: int):
    logger.info(f"Processing refund for tx#{tx_id}")
    for tx in transactions:
        if tx["tx_id"] == tx_id:
            if tx["status"] == "refunded":
                logger.warning(f"Transaction #{tx_id} already refunded")
                raise HTTPException(status_code=400, detail="Already refunded")
            tx["status"] = "refunded"
            logger.info(f"Refund completed for tx#{tx_id}")
            return tx
    logger.error(
        f"Transaction #{tx_id} not found for refund",
        extra={"api_endpoint": f"/api/refund/{tx_id}", "http_method": "POST"},
    )
    raise HTTPException(status_code=404, detail="Transaction not found")


@app.get("/api/exchange/{currency}")
async def get_exchange_rate(currency: str):
    """Endpoint that can trigger KeyError."""
    logger.info(f"Exchange rate lookup: {currency}")
    currency = currency.upper()
    if currency not in exchange_rates:
        logger.error(
            f"KeyError: exchange rate for '{currency}' not found in rates table",
            exc_info=True,
            extra={"api_endpoint": f"/api/exchange/{currency}", "http_method": "GET"},
        )
        raise HTTPException(status_code=404, detail=f"No rate for {currency}")
    return {"currency": currency, "rate": exchange_rates[currency]}


@app.get("/api/revenue")
async def revenue_summary():
    """Revenue summary - can trigger TypeError if bad data slips in."""
    logger.info("Computing revenue summary")
    try:
        total = sum(tx["usd_equivalent"] for tx in transactions if tx["status"] == "completed")
        return {"total_usd": round(total, 2), "transaction_count": len(transactions)}
    except TypeError:
        logger.error(
            "TypeError computing revenue: non-numeric usd_equivalent in transaction record",
            exc_info=True,
            extra={"api_endpoint": "/api/revenue", "http_method": "GET"},
        )
        raise HTTPException(status_code=500, detail="Revenue calculation error")


# ─── Entry point ──────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("payment_service:app", host="0.0.0.0", port=9002, reload=False)
