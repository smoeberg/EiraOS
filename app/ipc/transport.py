from __future__ import annotations

import socket
import sys
from pathlib import Path

from app.ipc.paths import run_dir, socket_path

DAEMON_PORTS = {
    "intent": 18766,
    "identity": 18767,
    "graph": 18768,
    "fleet": 18769,
}


def use_unix_sockets() -> bool:
    return hasattr(socket, "AF_UNIX") and sys.platform != "win32"


def port_file(daemon: str) -> Path:
    return run_dir() / f"{daemon}.port"


def endpoint_ready(daemon: str) -> bool:
    if use_unix_sockets():
        return socket_path(daemon).exists()
    path = port_file(daemon)
    return path.exists()


def read_port(daemon: str) -> int:
    if daemon in DAEMON_PORTS:
        return DAEMON_PORTS[daemon]
    return int(port_file(daemon).read_text(encoding="utf-8").strip())


def write_port(daemon: str, port: int) -> None:
    port_file(daemon).write_text(str(port), encoding="utf-8")


def remove_port(daemon: str) -> None:
    path = port_file(daemon)
    if path.exists():
        path.unlink()


def connect_socket(daemon: str, timeout: float) -> socket.socket:
    sock: socket.socket
    if use_unix_sockets():
        path = socket_path(daemon)
        if not path.exists():
            raise ConnectionError(f"Socket not found: {path}")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(str(path))
        return sock

    if not endpoint_ready(daemon):
        raise ConnectionError(
            f"Daemon not ready: {daemon}. Start: python -m app.daemons.runner"
        )
    port = read_port(daemon)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(("127.0.0.1", port))
    return sock


def bind_server(daemon: str) -> tuple[socket.socket, callable]:
    if use_unix_sockets():
        path = socket_path(daemon)
        if path.exists():
            path.unlink()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(path))

        def cleanup() -> None:
            if path.exists():
                path.unlink()

        return server, cleanup

    port = DAEMON_PORTS[daemon]
    write_port(daemon, port)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", port))

    def cleanup() -> None:
        remove_port(daemon)

    return server, cleanup
