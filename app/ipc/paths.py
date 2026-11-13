from __future__ import annotations

import os
import sys
from pathlib import Path

DAEMON_ALIASES = {
    "state": "stated",
    "stated": "stated",
    "identity": "identityd",
    "identityd": "identityd",
    "fleet": "fleetd",
    "fleetd": "fleetd",
    "veritas": "veritasd",
    "veritasd": "veritasd",
    "intent": "intentd",
    "intentd": "intentd",
    "graph": "graphd",
    "graphd": "graphd",
    "delegation": "delegationd",
    "delegationd": "delegationd",
    "model": "modeld",
    "modeld": "modeld",
}

# The model process runs as eira-model, which may not write /run/eira (owned
# by eira); its socket lives in its own runtime directory (systemd
# RuntimeDirectory=eira-model, group eira-clients).
MODEL_RUN_DIR = Path("/run/eira-model")

DAEMON_SOCKETS = {
    daemon: f"{daemon}.sock" for daemon in sorted(set(DAEMON_ALIASES.values()))
}


def canonical_daemon(daemon: str) -> str:
    try:
        return DAEMON_ALIASES[daemon]
    except KeyError as exc:
        raise KeyError(f"Unknown daemon: {daemon}") from exc


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
    canonical = canonical_daemon(daemon)
    if canonical == "modeld":
        env = os.getenv("EIRA_MODEL_RUN_DIR")
        if env:
            return Path(env) / DAEMON_SOCKETS[canonical]
        if sys.platform != "win32" and MODEL_RUN_DIR.is_dir():
            return MODEL_RUN_DIR / DAEMON_SOCKETS[canonical]
    return run_dir() / DAEMON_SOCKETS[canonical]


def ensure_run_dir() -> Path:
    path = run_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path
