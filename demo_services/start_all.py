"""
Start / Stop all demo services.

Usage:
    python start_all.py              Start all 4 services
    python start_all.py --equipped   Start only the 2 equipped services
    python start_all.py --bare       Start only the 2 non-equipped services
"""

import subprocess
import sys
import os
import signal
import time
from pathlib import Path

HERE = Path(__file__).parent

SERVICES = [
    {"name": "Inventory  (equipped)",     "module": "inventory_service",     "port": 9001},
    {"name": "Payment    (equipped)",     "module": "payment_service",      "port": 9002},
    {"name": "Notification (bare)",       "module": "notification_service", "port": 9003},
    {"name": "Analytics    (bare)",       "module": "analytics_service",    "port": 9004},
]


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--all"

    if mode == "--equipped":
        selected = SERVICES[:2]
    elif mode == "--bare":
        selected = SERVICES[2:]
    else:
        selected = SERVICES

    procs: list[subprocess.Popen] = []

    print("=" * 62)
    print("  AutoCure Demo Services Launcher")
    print("=" * 62)

    for svc in selected:
        print(f"  Starting {svc['name']}  ->  http://localhost:{svc['port']}")
        proc = subprocess.Popen(
            [sys.executable, "-u", str(HERE / f"{svc['module']}.py")],
            cwd=str(HERE),
            env={**os.environ},
        )
        procs.append(proc)
        time.sleep(0.5)

    print()
    print("  All services running.  Press Ctrl+C to stop.")
    print("=" * 62)

    try:
        while True:
            time.sleep(1)
            for i, proc in enumerate(procs):
                if proc.poll() is not None:
                    print(f"  [!] {selected[i]['name']} exited with code {proc.returncode}")
    except KeyboardInterrupt:
        print("\n  Stopping all services...")
        for proc in procs:
            proc.terminate()
        for proc in procs:
            proc.wait(timeout=5)
        print("  All services stopped.")


if __name__ == "__main__":
    main()
