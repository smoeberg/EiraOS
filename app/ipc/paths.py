from __future__ import annotations

import os
import sys
from pathlib import Path

DAEMON_SOCKETS = {
    "intent": "intent.sock",
    "identity": "identity.sock",
    "graph": "graph.sock",
    "fleet": "fleet.sock",
}


def run_dir() -> Path:
    env = os.getenv("EIRA_RUN_DIR")
    if env:
        return Path(env)
    if sys.platform != "win32":
        try:
            if os.geteuid() == 0 and Path("/run/eira").exists():
                return Path("/run/eira")
        except AttributeError:
            pass
    return Path(__file__).resolve().parent.parent.parent / "data" / "run"


def socket_path(daemon: str) -> Path:
    if daemon not in DAEMON_SOCKETS:
        raise KeyError(f"Unknown daemon: {daemon}")
    return run_dir() / DAEMON_SOCKETS[daemon]


def ensure_run_dir() -> Path:
    path = run_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path
