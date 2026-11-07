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

# Former write paths that bypassed the gate. They are not deleted (a deleted
# path tends to reappear as a copy elsewhere); they answer E_GATE_REQUIRED
# and point to the only way in.
# -32010 is AUTH_FAILED (app/ipc/auth.py); codes must be unique.
GATE_REQUIRED = -32040
REDIRECTED_METHODS = ("intent.confirm", "intent.execute", "journey.advance")


def gate_required(method: str):
    def handler(_params: dict[str, Any]) -> dict[str, Any]:
        raise JsonRpcError(
            GATE_REQUIRED,
            "E_GATE_REQUIRED",
            {
                "method": method,
                "use": "gate.propose",
                "user_message": "Handlingen skal foreslås og bekræftes gennem Gaten, før den udføres.",
            },
        )

    return handler


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
        lang = params.get("lang", "da")
        if not isinstance(lang, str):
            raise JsonRpcError(-32602, "lang must be a string")
        return active.propose(_edp_input(params), params.get("session_id"), _origin(params), lang).to_dict()

    def consent(params: dict[str, Any]) -> dict[str, Any]:
        return active.grant_consent(
            _text(params, "action_id"),
            _text(params, "content_hash"),
            _text(params, "rendering_hash"),
            params.get("session_id"),
        ).to_dict()

    def confirm(params: dict[str, Any]) -> dict[str, Any]:
        return active.confirm(
            _text(params, "action_id"),
            _text(params, "content_hash"),
            _text(params, "rendering_hash"),
            params.get("session_id"),
        ).to_dict()

    def status(params: dict[str, Any]) -> dict[str, Any]:
        found = active.status(_text(params, "action_id"), params.get("session_id"))
        if found is None:
            raise JsonRpcError(-32004, "unknown action")
        return found

    def capabilities(_params: dict[str, Any]) -> dict[str, Any]:
        """Read-only: which families and system operations the gate accepts,
        and whether logind would allow each power action right now."""
        from app.gate.executors import POWER_METHODS, PowerExecutor
        from app.gate.system import OPERATIONS

        power = active._registry.executor("system:power.request_action")
        probe = power if isinstance(power, PowerExecutor) else None
        return {
            "families": ["edp", "eira_system"],
            "system_operations": sorted(OPERATIONS),
            "power": {action: probe.availability(action) if probe else "error" for action in POWER_METHODS},
        }

    server.register("gate.capabilities", capabilities)
    server.register("gate.propose", propose)
    server.register("gate.consent", consent)
    server.register("gate.confirm", confirm)
    server.register("gate.status", status)
    return active
