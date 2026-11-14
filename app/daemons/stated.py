from __future__ import annotations

import os
import time
from typing import Any
from uuid import UUID, uuid4

from app.core.audit import StateAuditTrail
from app.core.state import State
from app.core.store import StateStore
from app.ipc.access import daemon_write, read
from app.ipc.jsonrpc import JsonRpcError


def _create_store() -> Any:
    db_path = os.environ.get("EIRA_STATE_DB", "eira_state.db")
    backend = os.environ.get("EIRA_STATE_BACKEND", "auto").strip().casefold()
    if backend not in {"auto", "python", "rust"}:
        raise RuntimeError("EIRA_STATE_BACKEND must be auto, python, or rust")
    if backend != "python":
        try:
            from app.core_rust import RustBackendUnavailable, RustStateStore

            return RustStateStore(db_path)
        except RustBackendUnavailable:
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


def _sync_state(item: Any) -> State:
    if not isinstance(item, dict):
        raise ValueError("a synced state must be an object")
    return State(
        id=UUID(item["id"]),
        version=item["version"],
        timestamp_ns=item.get("timestamp_ns", 0),
        type=item["type"],
        payload=item["payload"],
        previous_state_id=(
            UUID(item["previous_state_id"]) if item.get("previous_state_id") else None
        ),
        hash=item.get("hash", ""),
    )


def state_sync_push(params: dict[str, Any]) -> dict[str, Any]:
    """All or nothing before the first write (fundregister S-2), like
    fleetd's push_blocks: one invalid state rejects the whole batch."""
    items = params.get("states", [])
    if not isinstance(items, list):
        raise JsonRpcError(-32602, "states must be a list")
    pending: list[State] = []
    invalid = 0
    for item in items:
        try:
            state = _sync_state(item)
        except (KeyError, TypeError, ValueError):
            invalid += 1
            continue
        if not state.is_hash_valid():
            invalid += 1
            continue
        pending.append(state)

    batch: dict[UUID, State] = {}
    new: list[State] = []
    skipped = 0
    for state in pending:
        seen = batch.get(state.id) or _store.get_by_id(state.id)
        if seen is not None:
            if seen.hash != state.hash:
                invalid += 1  # same id, different content: a conflict, never a write
            else:
                skipped += 1
            continue
        batch[state.id] = state
        new.append(state)

    if invalid:
        return {"status": "rejected", "accepted": 0, "skipped": 0, "invalid": invalid}
    for state in new:
        _store.append(state)
    return {"status": "synced", "accepted": len(new), "skipped": skipped, "invalid": 0}


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
    # Writes only from named daemons running as the service user (fundregister
    # S-1, UDVIKLINGSPLAN F1c.3): the desktop user is in eira-clients and may
    # reach this socket, and the same UID does not make a caller a daemon.
    # fleetd writes the states it receives from paired devices (sync.push_blocks).
    server.register("state.append", daemon_write(state_append, callers=("fleetd",)))
    server.register("state.get", read(state_get))
    server.register("state.get_by_hash", read(state_get_by_hash))
    server.register("state.get_history", read(state_get_history))
    server.register("state.list", read(state_list))
    # No daemon calls the batch path today (fleetd appends one state at a time).
    server.register("state.sync_push", daemon_write(state_sync_push, callers=()))
    server.register("state.sync_pull", read(state_sync_pull))
    # identityd audits certificate checks; delegationd creates and revokes.
    server.register(
        "audit.append", daemon_write(audit_append, callers=("identityd", "delegationd"))
    )
    server.register("audit.verify", read(audit_verify))
    server.register("health", read(lambda _: {"daemon": "eira-stated", "ok": True}))
