#!/usr/bin/env python3
"""Smoke test for EIRA IPC daemons."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.daemons.runner import start_daemons, stop_daemons
from app.ipc.client import IpcClient
from app.ipc.jsonrpc import JsonRpcError


def main() -> int:
    start_daemons()
    time.sleep(0.3)
    try:
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
            intent.call("intent.confirm", {"intent_id": planned["intent_id"]})
            print("intent.confirm: unexpected success without step-up")
            return 1
        except JsonRpcError as exc:
            print("intent.confirm (expected block):", exc.data.get("user_message", exc.message))

        identity.call("identity.step_up", {"required_assurance": "org_acting"})
        confirmed = intent.call("intent.confirm", {"intent_id": planned["intent_id"]})
        print("intent.confirm after step-up:", confirmed["status"])

        print("\nIPC smoke test OK")
        return 0
    finally:
        stop_daemons()


if __name__ == "__main__":
    sys.exit(main())
