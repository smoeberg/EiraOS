from __future__ import annotations

import os
import time
from typing import Any
from uuid import UUID, uuid4

from app.core.state import State
from app.core.store import StateStore
from app.ipc.jsonrpc import JsonRpcError

_store = StateStore(os.environ.get("EIRA_STATE_DB", "eira_state.db"))


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
        if state.hash != state.compute_hash():
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


def state_get_history(params: dict[str, Any]) -> list[dict[str, Any]]:
    latest_id_str = params.get("latest_state_id")
    if not latest_id_str:
        raise JsonRpcError(-32602, "latest_state_id is required")
    return [
        state.model_dump(mode="json")
        for state in _store.get_history(UUID(latest_id_str))
    ]


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
            if state.hash != state.compute_hash():
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


def register_state_handlers(server: Any) -> None:
    server.register("state.append", state_append)
    server.register("state.get", state_get)
    server.register("state.get_history", state_get_history)
    server.register("state.sync_push", state_sync_push)
    server.register("state.sync_pull", state_sync_pull)
    server.register("health", lambda _: {"daemon": "eira-stated", "ok": True})
