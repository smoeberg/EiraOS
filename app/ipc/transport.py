from __future__ import annotations

import socket
import sys
from collections.abc import Callable
from pathlib import Path

from app.ipc.paths import canonical_daemon, run_dir, socket_path
from app.ipc.socket_security import remove_unix_socket, setup_unix_socket

DAEMON_PORTS = {
    "stated": 18765,
    "intentd": 18766,
    "identityd": 18767,
    "graphd": 18768,
    "fleetd": 18769,
    "veritasd": 18770,
}


def use_unix_sockets() -> bool:
    return hasattr(socket, "AF_UNIX") and sys.platform != "win32"


def port_file(daemon: str) -> Path:
    return run_dir() / f"{canonical_daemon(daemon)}.port"


def endpoint_ready(daemon: str) -> bool:
    if use_unix_sockets():
        return socket_path(daemon).exists()
    return port_file(daemon).exists()


def read_port(daemon: str) -> int:
    canonical = canonical_daemon(daemon)
    if canonical in DAEMON_PORTS:
        return DAEMON_PORTS[canonical]
    return int(port_file(canonical).read_text(encoding="utf-8").strip())


def write_port(daemon: str, port: int) -> None:
    port_file(daemon).write_text(str(port), encoding="utf-8")


def remove_port(daemon: str) -> None:
    try:
        port_file(daemon).unlink()
    except FileNotFoundError:
        pass


def connect_socket(daemon: str, timeout: float) -> socket.socket:
    canonical = canonical_daemon(daemon)
    sock: socket.socket
    if use_unix_sockets():
        path = socket_path(canonical)
        if not path.exists():
            raise ConnectionError(f"Socket not found: {path}")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(str(path))
        return sock

    if not endpoint_ready(canonical):
        raise ConnectionError(
            f"Daemon not ready: {canonical}. Start: python -m app.daemons.runner"
        )
    port = read_port(canonical)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(("127.0.0.1", port))
    return sock


def bind_server(daemon: str) -> tuple[socket.socket, Callable[[], None]]:
    canonical = canonical_daemon(daemon)
    if use_unix_sockets():
        path = socket_path(canonical)
        server = setup_unix_socket(str(path))

        def cleanup() -> None:
            remove_unix_socket(str(path))

        return server, cleanup

    port = DAEMON_PORTS[canonical]
    write_port(canonical, port)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", port))

    def cleanup() -> None:
        remove_port(canonical)

    return server, cleanup
