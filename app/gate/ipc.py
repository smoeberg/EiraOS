"""IPC-metoder for Gate Kernel i intentd (JSON-RPC er kommandotransport).

Der findes bevidst ingen metode, der kalder en executor: den eneste vej til
udførelse er ``gate.confirm``, som kører alle otte lag igen.
"""

from __future__ import annotations

import json
from typing import Any

from app.gate.kernel import Gate
from app.gate.policy import Origin
from app.ipc.jsonrpc import JsonRpcError

_GATE: Gate | None = None


def default_gate() -> Gate:
    global _GATE
    if _GATE is None:
        _GATE = Gate()
    return _GATE


def _text(params: dict[str, Any], name: str) -> str:
    value = params.get(name)
    if not isinstance(value, str) or not value:
        raise JsonRpcError(-32602, f"{name} is required")
    return value


def _edp_input(params: dict[str, Any]) -> str | None:
    value = params.get("edp")
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, str):
        return value
    return None  # the gate rejects it as E_SYNTAX


def _origin(params: dict[str, Any]) -> Origin:
    try:
        return Origin(params.get("origin", "user"))
    except ValueError:
        raise JsonRpcError(-32602, "origin must be 'user' or 'model'") from None


def register_gate_handlers(server, gate: Gate | None = None) -> Gate:
    active = gate or default_gate()

    def propose(params: dict[str, Any]) -> dict[str, Any]:
        return active.propose(_edp_input(params), params.get("session_id"), _origin(params)).to_dict()

    def consent(params: dict[str, Any]) -> dict[str, Any]:
        return active.grant_consent(
            _text(params, "action_id"), _text(params, "content_hash"), params.get("session_id")
        ).to_dict()

    def confirm(params: dict[str, Any]) -> dict[str, Any]:
        return active.confirm(
            _text(params, "action_id"), _text(params, "content_hash"), params.get("session_id")
        ).to_dict()

    def status(params: dict[str, Any]) -> dict[str, Any]:
        found = active.status(_text(params, "action_id"), params.get("session_id"))
        if found is None:
            raise JsonRpcError(-32004, "unknown action")
        return found

    server.register("gate.propose", propose)
    server.register("gate.consent", consent)
    server.register("gate.confirm", confirm)
    server.register("gate.status", status)
    return active
