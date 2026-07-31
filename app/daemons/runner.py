from __future__ import annotations

import atexit
import signal
import sys
import time

from app.capability import seed_adapter_health, seed_capabilities
from app.daemons.base import JsonRpcServer
from app.daemons.fleetd import register_fleet_handlers
from app.daemons.graphd import register_graph_handlers
from app.daemons.identityd import register_identity_handlers
from app.daemons.intent_engine import register_intent_handlers
from app.ipc.paths import ensure_run_dir
from app.ipc.transport import use_unix_sockets
from app.seed import seed_if_empty

_servers: list[JsonRpcServer] = []


def _build_servers() -> list[JsonRpcServer]:
    ensure_run_dir()
    intent = JsonRpcServer("eira-intent-engine", "intent")
    register_intent_handlers(intent)

    identity = JsonRpcServer("eira-identityd", "identity")
    register_identity_handlers(identity)

    graph = JsonRpcServer("eira-object-graphd", "graph")
    register_graph_handlers(graph)

    fleet = JsonRpcServer("eira-fleetd", "fleet")
    register_fleet_handlers(fleet)

    return [intent, identity, graph, fleet]


def start_daemons() -> list[JsonRpcServer]:
    global _servers
    if _servers:
        return _servers

    seed_if_empty()
    seed_capabilities()
    seed_adapter_health()

    _servers = _build_servers()
    for server in _servers:
        server.start()

    atexit.register(stop_daemons)
    return _servers


def stop_daemons() -> None:
    global _servers
    for server in _servers:
        server.stop()
    _servers = []


def main() -> None:
    servers = start_daemons()
    transport = "unix" if use_unix_sockets() else "tcp"
    print(f"EIRA daemons running ({transport}):")
    for server in servers:
        print(f"  {server.name} ({server.daemon})")
    print("Press Ctrl+C to stop")

    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_daemons()
        print("Stopped.")


if __name__ == "__main__":
    main()


def start_veritasd():
    from app.daemons.veritasd import VeritasDaemon
    v = VeritasDaemon()
    v.run_loop()
