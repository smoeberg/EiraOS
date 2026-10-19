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
    "walletd",
    "presenced",
    "contextd",
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


def _register_walletd(server: JsonRpcServer) -> None:
    from app.daemons.walletd import WalletDaemon

    wallet = WalletDaemon()

    def optimize_and_pay(params: dict[str, Any]) -> dict[str, Any]:
        amount = params.get("amount_dkk")
        merchant = params.get("merchant")
        rails = params.get("supported_rails", [])
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount <= 0:
            from app.ipc.jsonrpc import INVALID_PARAMS, JsonRpcError

            raise JsonRpcError(INVALID_PARAMS, "amount_dkk must be a positive number")
        if not isinstance(merchant, str) or not merchant.strip():
            from app.ipc.jsonrpc import INVALID_PARAMS, JsonRpcError

            raise JsonRpcError(INVALID_PARAMS, "merchant must be a non-empty string")
        if not isinstance(rails, list) or not all(isinstance(rail, str) for rail in rails):
            from app.ipc.jsonrpc import INVALID_PARAMS, JsonRpcError

            raise JsonRpcError(INVALID_PARAMS, "supported_rails must be a list of strings")
        return wallet.optimize_and_pay(float(amount), merchant, rails)

    server.register("wallet.optimize_and_pay", optimize_and_pay)
    server.register("wallet.list_credentials", lambda _: wallet.list_credentials())
    server.register("health", lambda _: {"daemon": "eira-walletd", "ok": True})


def _register_presenced(server: JsonRpcServer) -> None:
    from app.daemons.presenced import PresenceDaemon
    from app.ipc.jsonrpc import INVALID_PARAMS, JsonRpcError

    presence = PresenceDaemon()

    def annotate(params: dict[str, Any]) -> dict[str, Any]:
        object_id = params.get("object_id")
        author = params.get("author")
        comment = params.get("comment")
        decision_point = params.get("decision_point", False)
        if not all(isinstance(value, str) and value.strip() for value in (object_id, author, comment)):
            raise JsonRpcError(INVALID_PARAMS, "object_id, author and comment are required")
        if not isinstance(decision_point, bool):
            raise JsonRpcError(INVALID_PARAMS, "decision_point must be a boolean")
        return presence.annotate_object(object_id, author, comment, decision_point)

    def get_presence(params: dict[str, Any]) -> dict[str, Any]:
        object_id = params.get("object_id")
        if not isinstance(object_id, str) or not object_id.strip():
            raise JsonRpcError(INVALID_PARAMS, "object_id is required")
        return presence.get_object_presence(object_id)

    server.register("presence.annotate_object", annotate)
    server.register("presence.get_object", get_presence)
    server.register("health", lambda _: {"daemon": "eira-presenced", "ok": True})


def _register_contextd(server: JsonRpcServer) -> None:
    from app.daemons.contextd import ContextDaemon
    from app.ipc.jsonrpc import INVALID_PARAMS, JsonRpcError

    context = ContextDaemon()

    def set_context(params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("context_name")
        if not isinstance(name, str) or not name.strip():
            raise JsonRpcError(INVALID_PARAMS, "context_name is required")
        result = context.set_context(name)
        if result.get("status") == "ERROR":
            raise JsonRpcError(INVALID_PARAMS, result["message"])
        return result

    server.register("context.get", lambda _: context.get_context())
    server.register("context.set", set_context)
    server.register("health", lambda _: {"daemon": "eira-contextd", "ok": True})


REGISTRARS: dict[str, Callable[[JsonRpcServer], None]] = {
    "stated": _register_stated,
    "identityd": _register_identityd,
    "fleetd": _register_fleetd,
    "veritasd": _register_veritasd,
    "intentd": _register_intentd,
    "graphd": _register_graphd,
    "walletd": _register_walletd,
    "presenced": _register_presenced,
    "contextd": _register_contextd,
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
    """Start one daemon or the complete nine-daemon set in background threads."""
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
