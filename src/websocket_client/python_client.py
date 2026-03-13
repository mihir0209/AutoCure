"""
WebSocket Client Snippet for Python Services
Self-Healing Software System v2.0

Add this to your Python service to stream logs to the Self-Healing system.

Usage:
    1. Copy this file to your project
    2. Import and initialize the client
    3. Use the logger to send logs

Example:
    from self_healer_client import SelfHealerClient
    
    # Initialize (once at startup)
    client = SelfHealerClient(
        server_url="ws://localhost:9292/ws/logs/your-user-id",
        service_name="my-service"
    )
    client.connect()
    
    # Log messages (anywhere in your code)
    client.info("User logged in", {"user_id": 123})
    client.error("Failed to process request", {"error": str(e)}, payload=request_data)
"""

import asyncio
import json
import threading
import queue
from datetime import datetime
from typing import Optional, Dict, Any
import logging

# Try to import websockets library
try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    print("Warning: 'websockets' package not installed. Run: pip install websockets")


class SelfHealerClient:
    """
    WebSocket client for streaming logs to the Self-Healing system.
    
    Features:
    - Async WebSocket connection with auto-reconnect
    - Thread-safe log queue
    - Automatic payload inclusion
    - Support for autocure-try flag
    """
    
    def __init__(
        self,
        server_url: str,
        service_name: str = "unknown",
        auto_reconnect: bool = True,
        reconnect_delay: float = 5.0,
    ):
        """
        Initialize the Self-Healer client.
        
        Args:
            server_url: WebSocket URL (e.g., ws://localhost:9292/ws/logs/user123)
            service_name: Name of your service for identification
            auto_reconnect: Whether to automatically reconnect on disconnect
            reconnect_delay: Seconds to wait before reconnecting
        """
        if not WEBSOCKETS_AVAILABLE:
            raise ImportError("websockets package is required. Run: pip install websockets")
        
        self.server_url = server_url
        self.service_name = service_name
        self.auto_reconnect = auto_reconnect
        self.reconnect_delay = reconnect_delay
        
        self._log_queue: queue.Queue = queue.Queue()
        self._websocket = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        
    def connect(self):
        """Start the WebSocket connection in a background thread."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self._thread.start()
        
    def disconnect(self):
        """Disconnect and stop the background thread."""
        self._running = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=2.0)
    
    def _run_event_loop(self):
        """Run the async event loop in a thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        
        try:
            self._loop.run_until_complete(self._connection_loop())
        except Exception as e:
            logging.error(f"Self-Healer client error: {e}")
        finally:
            self._loop.close()
    
    async def _connection_loop(self):
        """Main connection loop with auto-reconnect."""
        while self._running:
            try:
                async with websockets.connect(self.server_url) as websocket:
                    self._websocket = websocket
                    logging.info(f"Connected to Self-Healer at {self.server_url}")
                    
                    # Start sender and receiver tasks
                    sender_task = asyncio.create_task(self._sender())
                    receiver_task = asyncio.create_task(self._receiver())
                    
                    # Wait for either to complete (usually on disconnect)
                    done, pending = await asyncio.wait(
                        [sender_task, receiver_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    
                    # Cancel pending tasks
                    for task in pending:
                        task.cancel()
                        
            except Exception as e:
                logging.warning(f"Self-Healer connection error: {e}")
                
            self._websocket = None
            
            if self._running and self.auto_reconnect:
                logging.info(f"Reconnecting in {self.reconnect_delay}s...")
                await asyncio.sleep(self.reconnect_delay)
    
    async def _sender(self):
        """Send queued log messages."""
        while self._running:
            try:
                # Check queue with timeout
                try:
                    log_entry = self._log_queue.get(timeout=0.1)
                except queue.Empty:
                    await asyncio.sleep(0.1)
                    continue
                
                if self._websocket:
                    await self._websocket.send(json.dumps(log_entry))
                    
            except Exception as e:
                logging.error(f"Error sending log: {e}")
                break
    
    async def _receiver(self):
        """Receive messages from the server."""
        while self._running and self._websocket:
            try:
                message = await self._websocket.recv()
                data = json.loads(message)
                
                # Handle server messages
                msg_type = data.get("type", "")
                
                if msg_type == "error_received":
                    logging.debug("Self-Healer acknowledged error")
                elif msg_type == "error":
                    logging.warning(f"Self-Healer error: {data.get('payload', {}).get('message')}")
                    
            except Exception as e:
                logging.error(f"Error receiving message: {e}")
                break
    
    def _queue_log(
        self,
        level: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
        api_endpoint: Optional[str] = None,
        http_method: Optional[str] = None,
        stack_trace: Optional[str] = None,
        is_autocure_try: bool = False,
    ):
        """Queue a log entry for sending."""
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "message": message,
            "source": self.service_name,
            "metadata": metadata,
            "payload": payload,
            "api_endpoint": api_endpoint,
            "http_method": http_method,
            "stack_trace": stack_trace,
            "is_autocure_try": is_autocure_try,
        }
        
        self._log_queue.put(log_entry)
    
    # Convenience methods for different log levels
    
    def debug(self, message: str, metadata: Optional[Dict] = None, **kwargs):
        """Log a debug message."""
        self._queue_log("DEBUG", message, metadata, **kwargs)
    
    def info(self, message: str, metadata: Optional[Dict] = None, **kwargs):
        """Log an info message."""
        self._queue_log("INFO", message, metadata, **kwargs)
    
    def warning(self, message: str, metadata: Optional[Dict] = None, **kwargs):
        """Log a warning message."""
        self._queue_log("WARNING", message, metadata, **kwargs)
    
    def error(
        self,
        message: str,
        metadata: Optional[Dict] = None,
        payload: Optional[Dict] = None,
        api_endpoint: Optional[str] = None,
        http_method: Optional[str] = None,
        exception: Optional[Exception] = None,
        **kwargs
    ):
        """
        Log an error message.
        
        Args:
            message: Error message
            metadata: Additional context
            payload: Request payload that caused the error
            api_endpoint: API endpoint where error occurred
            http_method: HTTP method (GET, POST, etc.)
            exception: Exception object (will extract stack trace)
        """
        import traceback
        
        stack_trace = None
        if exception:
            stack_trace = "".join(traceback.format_exception(
                type(exception), exception, exception.__traceback__
            ))
        
        self._queue_log(
            "ERROR", message, metadata, payload,
            api_endpoint, http_method, stack_trace,
            **kwargs
        )
    
    def critical(self, message: str, metadata: Optional[Dict] = None, **kwargs):
        """Log a critical message."""
        self._queue_log("CRITICAL", message, metadata, **kwargs)


# Convenience function for quick setup
def create_client(
    user_id: str,
    server_host: str = "localhost",
    server_port: int = 9292,
    service_name: str = "python-service",
) -> SelfHealerClient:
    """
    Create and connect a Self-Healer client.
    
    Args:
        user_id: Your user ID in the Self-Healing system
        server_host: Self-Healer server host
        server_port: Self-Healer server port
        service_name: Name of your service
        
    Returns:
        Connected SelfHealerClient instance
    """
    url = f"ws://{server_host}:{server_port}/ws/logs/{user_id}"
    client = SelfHealerClient(url, service_name)
    client.connect()
    return client


# Example usage
if __name__ == "__main__":
    # Example: Connect and send some test logs
    client = create_client(
        user_id="demo-user",
        service_name="demo-python-service"
    )
    
    import time
    
    try:
        print("Sending test logs...")
        
        client.info("Service started", {"version": "1.0.0"})
        time.sleep(1)
        
        client.info("Processing request", 
                   metadata={"request_id": "req-123"},
                   api_endpoint="/api/users",
                   http_method="POST",
                   payload={"name": "John", "email": "john@example.com"})
        time.sleep(1)
        
        # Simulate an error
        try:
            result = 1 / 0
        except Exception as e:
            client.error(
                "Division by zero error",
                metadata={"function": "calculate"},
                api_endpoint="/api/calculate",
                http_method="POST",
                payload={"dividend": 1, "divisor": 0},
                exception=e
            )
        
        time.sleep(2)
        print("Done! Check the Self-Healer server for received logs.")
        
    finally:
        client.disconnect()
