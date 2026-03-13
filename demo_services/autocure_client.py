"""
AutoCure WebSocket Client
Shared integration module used by equipped demo services.

Connects to the AutoCure platform via WebSocket, streams log entries in
real-time, and receives analysis results back.
"""

import asyncio
import json
import logging
import threading
import traceback
from datetime import datetime, timezone
from typing import Optional

try:
    import websockets
except ImportError:
    raise ImportError("Run: pip install websockets")


class AutoCureHandler(logging.Handler):
    """
    Python logging handler that streams log records to the AutoCure
    self-healing platform over a persistent WebSocket connection.

    Usage:
        handler = AutoCureHandler(
            ws_url="ws://localhost:9292/ws/logs/my-service",
            level=logging.DEBUG,      # send everything
        )
        logging.getLogger().addHandler(handler)
        handler.start_background()     # fire-and-forget thread
    """

    def __init__(
        self,
        ws_url: str,
        level: int = logging.DEBUG,
    ):
        super().__init__(level)
        self.ws_url = ws_url
        self._queue: asyncio.Queue = asyncio.Queue()
        self._ws = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._connected = False

    # ---- background thread ------------------------------------------------

    def start_background(self):
        """Spin up a daemon thread that manages the WebSocket connection."""
        self._thread = threading.Thread(target=self._run, daemon=True, name="autocure-ws")
        self._thread.start()

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._connect_loop())

    async def _connect_loop(self):
        backoff = 2
        while True:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    self._ws = ws
                    self._connected = True
                    backoff = 2
                    print(f"[AutoCure] Connected to {self.ws_url}")

                    # Drain queue
                    while not self._queue.empty():
                        msg = self._queue.get_nowait()
                        await ws.send(msg)

                    # Keep reading (server may send analysis results)
                    while True:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=30)
                            data = json.loads(raw)
                            msg_type = data.get("type", "")
                            if msg_type == "analysis_complete":
                                payload = data.get("payload", {})
                                print(f"[AutoCure] Analysis result: "
                                      f"confidence={payload.get('confidence', '?')}%, "
                                      f"root_cause={payload.get('root_cause', '?')[:80]}")
                            elif msg_type == "error_received":
                                print("[AutoCure] Error acknowledged by platform")
                        except asyncio.TimeoutError:
                            await ws.ping()
            except Exception as exc:
                self._ws = None
                self._connected = False
                print(f"[AutoCure] Connection lost ({exc}), retrying in {backoff}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    # ---- logging handler ---------------------------------------------------

    def emit(self, record: logging.LogRecord):
        entry = {
            "message": record.getMessage(),
            "level": record.levelname,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_file": getattr(record, "source_file", record.pathname),
            "line_number": record.lineno,
            "logger_name": record.name,
        }
        if record.exc_info and record.exc_info[0]:
            entry["stack_trace"] = "".join(traceback.format_exception(*record.exc_info))
        # extra fields (optional)
        for attr in ("api_endpoint", "http_method", "response_status"):
            val = getattr(record, attr, None)
            if val is not None:
                entry[attr] = val

        payload = json.dumps(entry)
        if self._ws and self._loop and self._connected:
            asyncio.run_coroutine_threadsafe(self._ws.send(payload), self._loop)
        else:
            try:
                self._queue.put_nowait(payload)
            except Exception:
                pass

    @property
    def is_connected(self) -> bool:
        return self._connected
