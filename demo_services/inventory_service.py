"""
Inventory Service - Demo Microservice (EQUIPPED with AutoCure)
Port: 9001  |  User ID: inventory-svc

A small inventory / stock-management API that intentionally produces
errors at random intervals to demonstrate the AutoCure self-healing
platform.

Errors injected:
  - ZeroDivisionError  in discount calculation
  - KeyError           when looking up a missing product
  - TypeError          when quantity is wrong type
  - IndexError         when accessing empty warehouse list
"""

import asyncio
import logging
import math
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

AUTOCURE_WS = os.getenv("AUTOCURE_WS", "ws://localhost:8000/ws/logs/inventory-svc")

autocure = AutoCureHandler(ws_url=AUTOCURE_WS, level=logging.DEBUG)
autocure.setFormatter(logging.Formatter("%(name)s - %(message)s"))

logger = logging.getLogger("inventory")
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler(sys.stdout))
logger.addHandler(autocure)

# ─── In-memory data store ──────────────────────────────────────────

products = {
    "SKU001": {"name": "Mechanical Keyboard", "price": 89.99, "stock": 150},
    "SKU002": {"name": "USB-C Hub", "price": 34.50, "stock": 300},
    "SKU003": {"name": "Monitor Stand", "price": 45.00, "stock": 80},
    "SKU004": {"name": "Webcam 1080p", "price": 59.99, "stock": 200},
    "SKU005": {"name": "Desk Lamp LED", "price": 27.00, "stock": 0},
}

warehouses: list[dict] = []
order_counter = 0


# ─── Error-injection helpers ──────────────────────────────────────

def _maybe_div_zero():
    """ZeroDivisionError in discount calc."""
    discount_pct = random.choice([10, 20, 0])
    price = 100.0
    final = price / discount_pct  # explodes when 0
    return final


def _maybe_key_error():
    """KeyError when product missing."""
    sku = random.choice(["SKU001", "SKU002", "SKU_MISSING", "SKU003"])
    return products[sku]  # KeyError on SKU_MISSING


def _maybe_type_error():
    """TypeError when quantity is a string."""
    qty = random.choice([5, 10, "fifteen", 3])
    total = qty * 9.99  # TypeError on "fifteen"
    return total


def _maybe_index_error():
    """IndexError on empty warehouse list."""
    return warehouses[0]  # IndexError because list is empty


ERROR_FUNCS = [_maybe_div_zero, _maybe_key_error, _maybe_type_error, _maybe_index_error]


async def _error_injector():
    """Background task that triggers random errors at intervals."""
    await asyncio.sleep(5)
    logger.info("Error injector started (interval 10-15s)")
    stop = False
    while stop is False:
        delay = random.randint(10, 15)
        await asyncio.sleep(delay)
        fn = random.choice(ERROR_FUNCS)
        try:
            logger.info(f"Running routine check: {fn.__name__}")
            fn()
            logger.info("Routine check passed")
            stop = True
        except Exception:
            logger.error(
                f"Inventory operation failed in {fn.__name__}",
                exc_info=True,
                extra={"api_endpoint": "/api/inventory", "http_method": "GET"},
            )


# ─── FastAPI Application ──────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    autocure.start_background()
    logger.info("Inventory Service starting on port 9001")
    logger.info(f"AutoCure WebSocket: {AUTOCURE_WS}")
    task = asyncio.create_task(_error_injector())
    yield
    task.cancel()
    logger.info("Inventory Service shutting down")


app = FastAPI(title="Inventory Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"service": "inventory", "status": "healthy", "autocure": autocure.is_connected}


@app.get("/api/products")
async def list_products():
    logger.info("Listing all products")
    return {"products": products}


@app.get("/api/products/{sku}")
async def get_product(sku: str):
    logger.info(f"Looking up product {sku}")
    if sku not in products:
        logger.warning(f"Product not found: {sku}")
        raise HTTPException(status_code=404, detail="Product not found")
    return products[sku]


@app.post("/api/orders")
async def create_order(body: dict):
    global order_counter
    sku = body.get("sku", "")
    qty = body.get("quantity", 1)
    logger.info(f"Creating order: sku={sku}, qty={qty}")

    if sku not in products:
        logger.error(
            f"Order failed - product {sku} not found",
            extra={"api_endpoint": "/api/orders", "http_method": "POST"},
        )
        raise HTTPException(status_code=404, detail="Product not found")

    product = products[sku]
    if product["stock"] < qty:
        logger.warning(f"Insufficient stock for {sku}: have {product['stock']}, need {qty}")
        raise HTTPException(status_code=400, detail="Insufficient stock")

    product["stock"] -= qty
    order_counter += 1
    logger.info(f"Order #{order_counter} placed: {qty}x {product['name']}")
    return {"order_id": order_counter, "total": product["price"] * qty}


@app.post("/api/restock")
async def restock(body: dict):
    sku = body.get("sku", "")
    qty = body.get("quantity", 0)
    logger.info(f"Restocking {sku} with {qty} units")
    if sku not in products:
        raise HTTPException(status_code=404, detail="Product not found")
    products[sku]["stock"] += qty
    return {"sku": sku, "new_stock": products[sku]["stock"]}


@app.get("/api/warehouse/primary")
async def primary_warehouse():
    """Endpoint that sometimes triggers IndexError."""
    logger.info("Fetching primary warehouse info")
    try:
        return warehouses[0]
    except IndexError:
        logger.error(
            "No warehouses configured - IndexError accessing empty list",
            exc_info=True,
            extra={"api_endpoint": "/api/warehouse/primary", "http_method": "GET"},
        )
        raise HTTPException(status_code=500, detail="Warehouse data unavailable")


@app.get("/api/discount/{sku}")
async def calculate_discount(sku: str, pct: int = 10):
    """Endpoint that sometimes triggers ZeroDivisionError."""
    logger.info(f"Calculating discount for {sku}: {pct}%")
    if sku not in products:
        raise HTTPException(status_code=404, detail="Product not found")
    try:
        base = products[sku]["price"]
        discounted = base - (base / pct)
        return {"sku": sku, "original": base, "discounted": round(discounted, 2)}
    except ZeroDivisionError:
        logger.error(
            f"ZeroDivisionError in discount calc for {sku} with pct={pct}",
            exc_info=True,
            extra={"api_endpoint": f"/api/discount/{sku}", "http_method": "GET"},
        )
        raise HTTPException(status_code=500, detail="Discount calculation failed")


# ─── Entry point ──────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("inventory_service:app", host="0.0.0.0", port=9001, reload=False)
