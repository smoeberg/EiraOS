from __future__ import annotations

import os
import time
from typing import Any
from uuid import UUID, uuid4

from app.core.state import State
from app.core.store import StateStore
from app.core.audit import StateAuditTrail
from app.ipc.jsonrpc import JsonRpcError

def _create_store() -> Any:
    db_path = os.environ.get("EIRA_STATE_DB", "eira_state.db")
    backend = os.environ.get("EIRA_STATE_BACKEND", "auto").strip().casefold()
    if backend not in {"auto", "python", "rust"}:
        raise RuntimeError("EIRA_STATE_BACKEND must be auto, python, or rust")
    if backend != "python":
        try:
            from app.core_rust import RustStateStore

            return RustStateStore(db_path)
        except Exception:
            if backend == "rust":
                raise
    return StateStore(db_path)


_store = _create_store()
_audit_store: Any | None = None
_audit_trail: StateAuditTrail | None = None


def _active_audit_trail() -> StateAuditTrail:
    global _audit_store, _audit_trail
    if _audit_store is not _store or _audit_trail is None:
        _audit_store = _store
        _audit_trail = StateAuditTrail(_store)
    return _audit_trail


def state_append(params: dict[str, Any]) -> dict[str, Any]:
    try:
        state = State(
            id=UUID(params["id"]) if "id" in params else uuid4(),
            version=params.get("version", 1),
            timestamp_ns=params.get("timestamp_ns") or time.time_ns(),
            type=params["type"],
            payload=params["payload"],
            previous_state_id=(
                UUID(params["previous_state_id"])
                if params.get("previous_state_id")
                else None
            ),
            hash=params.get("hash", ""),
        )
        if not state.is_hash_valid():
            raise ValueError("State hash does not match canonical state content")
        _store.append(state)
        return {"status": "ok", "state_id": str(state.id), "hash": state.hash}
    except Exception as exc:
        raise JsonRpcError(-32602, f"Failed to append state: {exc}") from exc


def state_get(params: dict[str, Any]) -> dict[str, Any]:
    state_id_str = params.get("state_id")
    if not state_id_str:
        raise JsonRpcError(-32602, "state_id is required")
    state = _store.get_by_id(UUID(state_id_str))
    if not state:
        raise JsonRpcError(-32602, f"State not found: {state_id_str}")
    return state.model_dump(mode="json")


def state_get_by_hash(params: dict[str, Any]) -> dict[str, Any]:
    state_hash = str(params.get("hash") or "")
    if len(state_hash) != 64 or any(
        character not in "0123456789abcdef" for character in state_hash.casefold()
    ):
        raise JsonRpcError(-32602, "a SHA3-256 hash is required")
    state = _store.get_by_hash(state_hash)
    if not state:
        raise JsonRpcError(-32602, f"State not found: {state_hash}")
    return state.model_dump(mode="json")


def state_get_history(params: dict[str, Any]) -> list[dict[str, Any]]:
    latest_id_str = params.get("latest_state_id")
    if not latest_id_str:
        raise JsonRpcError(-32602, "latest_state_id is required")
    return [
        state.model_dump(mode="json")
        for state in _store.get_history(UUID(latest_id_str))
    ]


def state_list(params: dict[str, Any]) -> dict[str, Any]:
    limit = max(1, min(int(params.get("limit", 500)), 10_000))
    states = _store.list_states()
    selected = states[-limit:]
    return {
        "states": [state.model_dump(mode="json") for state in selected],
        "count": _store.count(),
    }


def state_sync_push(params: dict[str, Any]) -> dict[str, Any]:
    accepted = 0
    skipped = 0
    for item in params.get("states", []):
        try:
            state = State(
                id=UUID(item["id"]),
                version=item["version"],
                timestamp_ns=item.get("timestamp_ns", 0),
                type=item["type"],
                payload=item["payload"],
                previous_state_id=(
                    UUID(item["previous_state_id"])
                    if item.get("previous_state_id")
                    else None
                ),
                hash=item.get("hash", ""),
            )
            if not state.is_hash_valid():
                raise ValueError("State hash does not match canonical state content")
            if _store.get_by_id(state.id):
                skipped += 1
                continue
            _store.append(state)
            accepted += 1
        except Exception:
            skipped += 1
    return {"status": "synced", "accepted": accepted, "skipped": skipped}


def state_sync_pull(params: dict[str, Any]) -> dict[str, Any]:
    latest_id_str = params.get("latest_state_id")
    if not latest_id_str:
        return {"states": []}
    history = _store.get_history(UUID(latest_id_str))
    return {"states": [state.model_dump(mode="json") for state in history]}


def audit_append(params: dict[str, Any]) -> dict[str, Any]:
    event_type = str(params.get("event_type") or "")
    details = params.get("details") or {}
    if not isinstance(details, dict):
        raise JsonRpcError(-32602, "audit details must be an object")
    try:
        state = _active_audit_trail().append(
            event_type,
            details,
            actor_id=str(params.get("actor_id") or "system"),
        )
    except (TypeError, ValueError) as exc:
        raise JsonRpcError(-32602, str(exc)) from exc
    return {"status": "appended", "state_id": str(state.id), "hash": state.hash}


def audit_verify(params: dict[str, Any]) -> dict[str, Any]:
    expected_events = params.get("expected_events")
    return _active_audit_trail().verify(
        expected_head_hash=(
            str(params["expected_head_hash"])
            if params.get("expected_head_hash")
            else None
        ),
        expected_events=int(expected_events) if expected_events is not None else None,
    ).as_dict()


def register_state_handlers(server: Any) -> None:
    server.register("state.append", state_append)
    server.register("state.get", state_get)
    server.register("state.get_by_hash", state_get_by_hash)
    server.register("state.get_history", state_get_history)
    server.register("state.list", state_list)
    server.register("state.sync_push", state_sync_push)
    server.register("state.sync_pull", state_sync_pull)
    server.register("audit.append", audit_append)
    server.register("audit.verify", audit_verify)
    server.register("health", lambda _: {"daemon": "eira-stated", "ok": True})
