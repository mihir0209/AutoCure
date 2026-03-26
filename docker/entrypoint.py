import os
import socket
import subprocess
import sys
import time


def wait_for(host: str, port: int, name: str, timeout_seconds: int) -> None:
    print(f"[entrypoint] Waiting for {name} at {host}:{port}...")
    start = time.time()
    while True:
        try:
            with socket.create_connection((host, port), timeout=3):
                print(f"[entrypoint] {name} is reachable at {host}:{port}")
                return
        except OSError:
            if time.time() - start > timeout_seconds:
                print(
                    f"[entrypoint] ERROR: Timed out waiting for {name} ({host}:{port})",
                    file=sys.stderr,
                )
                sys.exit(1)
            time.sleep(1)


def main() -> int:
    print("[entrypoint] Starting AutoCure container...")
    print(f"[entrypoint] Python: {sys.version.split()[0]}")

    timeout = int(os.getenv("WAIT_FOR_SERVICES_TIMEOUT", "60"))
    wait_for(os.getenv("DB_HOST", "postgres"), int(os.getenv("DB_PORT", "5432")), "PostgreSQL", timeout)
    wait_for(os.getenv("REDIS_HOST", "redis"), int(os.getenv("REDIS_PORT", "6379")), "Redis", timeout)

    host = os.getenv("SERVER_HOST", "0.0.0.0")
    port = os.getenv("SERVER_PORT", "9292")
    print(f"[entrypoint] Launching AutoCure on {host}:{port}")

    cmd = ["uvicorn", "src.main:app", "--host", host, "--port", port]
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
