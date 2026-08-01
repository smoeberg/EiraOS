"""Lifecycle runner for EiraOS JSON-RPC daemons."""

from __future__ import annotations

import argparse
import os
import signal
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from app.daemons.base import JsonRpcServer
from app.ipc.paths import run_dir

DAEMON_NAMES = (
    "stated",
    "identityd",
    "fleetd",
    "veritasd",
    "intentd",
    "graphd",
)

_SERVERS: dict[str, JsonRpcServer] = {}
_SERVERS_LOCK = threading.Lock()
_PROCESS_STOP = threading.Event()


def _register_stated(server: JsonRpcServer) -> None:
    from app.daemons.stated import register_state_handlers

    register_state_handlers(server)


def _register_identityd(server: JsonRpcServer) -> None:
    from app.daemons.identityd import register_identity_handlers

    register_identity_handlers(server)


def _register_fleetd(server: JsonRpcServer) -> None:
    from app.daemons.fleetd import register_fleet_handlers

    register_fleet_handlers(server)


def _register_veritasd(server: JsonRpcServer) -> None:
    from app.daemons.veritasd import register_veritas_handlers

    register_veritas_handlers(server)


def _register_intentd(server: JsonRpcServer) -> None:
    from app.daemons.intentd import register_intent_handlers

    register_intent_handlers(server)


def _register_graphd(server: JsonRpcServer) -> None:
    from app.daemons.graphd import register_graph_handlers

    register_graph_handlers(server)


REGISTRARS: dict[str, Callable[[JsonRpcServer], None]] = {
    "stated": _register_stated,
    "identityd": _register_identityd,
    "fleetd": _register_fleetd,
    "veritasd": _register_veritasd,
    "intentd": _register_intentd,
    "graphd": _register_graphd,
}


def _selected_daemons(daemon: str) -> tuple[str, ...]:
    if daemon == "all":
        return DAEMON_NAMES
    if daemon not in REGISTRARS:
        raise ValueError(f"Unknown daemon: {daemon}")
    return (daemon,)


def start_daemons(
    daemon: str = "all", socket_dir: str | os.PathLike[str] | None = None
) -> dict[str, JsonRpcServer]:
    """Start one daemon or the complete Sprint 2 daemon set in background threads."""
    requested = _selected_daemons(daemon)
    if socket_dir is not None:
        resolved_dir = str(Path(socket_dir).resolve())
        if _SERVERS and run_dir().resolve() != Path(resolved_dir):
            raise RuntimeError("Cannot change socket directory while daemons are running")
        os.environ["EIRA_RUN_DIR"] = resolved_dir

    started_now: list[str] = []
    try:
        with _SERVERS_LOCK:
            for name in requested:
                existing = _SERVERS.get(name)
                if existing is not None:
                    continue
                server = JsonRpcServer(name=f"eira-{name}", daemon=name)
                REGISTRARS[name](server)
                server.start()
                _SERVERS[name] = server
                started_now.append(name)
            return {name: _SERVERS[name] for name in requested}
    except BaseException:
        for name in reversed(started_now):
            server = _SERVERS.pop(name, None)
            if server:
                server.stop()
        raise


def stop_daemons() -> None:
    """Stop all active daemons and remove their socket files."""
    with _SERVERS_LOCK:
        servers = list(_SERVERS.items())
        _SERVERS.clear()
    for _, server in reversed(servers):
        server.stop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run EiraOS IPC daemons")
    parser.add_argument(
        "--daemon",
        choices=(*DAEMON_NAMES, "all"),
        default="all",
        help="Daemon to run (default: all)",
    )
    parser.add_argument(
        "--socket-dir",
        default="/run/eira",
        help="Unix socket directory (default: /run/eira)",
    )
    return parser


def _handle_shutdown(_signum: int, _frame: Any) -> None:
    _PROCESS_STOP.set()


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _PROCESS_STOP.clear()
    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)
    try:
        start_daemons(args.daemon, args.socket_dir)
        while not _PROCESS_STOP.wait(1.0):
            pass
    finally:
        stop_daemons()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
