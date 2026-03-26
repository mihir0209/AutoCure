import os
import socket
import subprocess
import sys
import time
from pathlib import Path


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


def _configure_git_safe_directories() -> None:
    """Allow git operations on bind-mounted repositories inside the container."""
    try:
        # In containers, wildcard safe.directory is the most reliable setting for
        # host-mounted repos that may have differing ownership metadata.
        proc = subprocess.run(
            ["git", "config", "--global", "--add", "safe.directory", "*"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if proc.returncode == 0:
            print("[entrypoint] Git safe.directory configured: *")
            return

        # Fallback for environments where wildcard is unavailable.
        repos_root = Path(os.getenv("REPOS_ROOT", "/app/repos"))
        candidates = [repos_root]
        if repos_root.exists():
            for p in repos_root.glob("*/*"):
                if p.is_dir():
                    candidates.append(p)

        for path in candidates:
            subprocess.run(
                ["git", "config", "--global", "--add", "safe.directory", str(path)],
                capture_output=True,
                text=True,
                timeout=15,
            )
        print(f"[entrypoint] Git safe.directory fallback applied to {len(candidates)} paths")
    except Exception as e:
        print(f"[entrypoint] WARNING: failed to configure git safe.directory: {e}")


def main() -> int:
    print("[entrypoint] Starting AutoCure container...")
    print(f"[entrypoint] Python: {sys.version.split()[0]}")

    _configure_git_safe_directories()

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
