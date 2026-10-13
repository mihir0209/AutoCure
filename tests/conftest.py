"""
Shared fixtures for stress/load tests.
Connects to the live AutoCure server running at localhost:9292.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import List

import pytest
import pytest_asyncio
from httpx import AsyncClient


def make_log(
    level: str = "INFO",
    message: str = "test log entry",
    source_file: str = "app.py",
    line_number: int = 42,
    stack_trace: str = None,
) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "message": message,
        "source_file": source_file,
        "line_number": line_number,
        "stack_trace": stack_trace,
    }


SERVER_HOST = "localhost"
SERVER_PORT = 9292
WS_BASE = f"ws://{SERVER_HOST}:{SERVER_PORT}/ws/logs"
API_BASE = f"http://{SERVER_HOST}:{SERVER_PORT}"


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(base_url=API_BASE, timeout=30.0) as c:
        yield c
