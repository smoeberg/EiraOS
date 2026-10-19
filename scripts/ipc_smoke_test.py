#!/usr/bin/env python3
"""Smoke test for all EiraOS IPC daemons."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.daemons.runner import DAEMON_NAMES, start_daemons, stop_daemons
from app.ipc.client import IpcClient
from app.ipc.jsonrpc import JsonRpcError


def main() -> int:
    start_daemons()
    time.sleep(0.3)
    try:
        # Every registered daemon must expose a working IPC socket and health method.
        for daemon in DAEMON_NAMES:
            health = IpcClient(daemon).call("health")
            if health.get("ok") is not True:
                raise AssertionError(f"{daemon} health check failed: {health}")
            print(f"{daemon}: health OK")

        intent = IpcClient("intent")
        graph = IpcClient("graph")
        identity = IpcClient("identity")

        dash = intent.call("dashboard.get", {"actor_id": "mette@kommune.dk"})
        print("dashboard.get:", dash["greeting"], f"({len(dash['trust_items'])} trust items)")

        planned = intent.call(
            "intent.plan",
            {"raw_input": "Godkend budget", "focus": "Kommunepilot"},
        )
        print("intent.plan:", planned["category"], planned["action"], f"can_execute={planned.get('can_execute')}")

        temporal = graph.call(
            "graph.temporal_query",
            {
                "from_name": "Lars",
                "to_name": "Mette",
                "as_of": "2024-03-15T12:00:00Z",
            },
        )
        print("graph.temporal_query:", len(temporal["relations"]), "relation(s)")

        session = identity.call("identity.session")
        print("identity.session:", session["assurance_level"])

        try:
            identity.call(
                "identity.step_up",
                {"required_assurance": "org_acting"},
                session_id=session.get("session_id"),
            )
            raise AssertionError("identity.step_up unexpectedly succeeded without a token")
        except JsonRpcError as exc:
            user_message = exc.data.get("user_message")
            if not user_message:
                raise AssertionError("step-up rejection omitted user_message") from exc
            print("identity.step_up (expected rejection):", user_message)

        print("\nIPC smoke test OK (all nine daemons)")
        return 0
    finally:
        stop_daemons()


if __name__ == "__main__":
    sys.exit(main())
