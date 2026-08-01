"""IPC-backed state-store adapters for non-owner daemons."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.core.state import State
from app.ipc.client import IpcClient
from app.ipc.jsonrpc import JsonRpcError


class RpcStateStore:
    """StateStore-compatible client that keeps SQLite ownership in stated."""

    def __init__(self, client: IpcClient | None = None) -> None:
        self.client = client or IpcClient("stated")

    @staticmethod
    def _state(value: dict[str, Any]) -> State:
        return State.model_validate(value)

    @staticmethod
    def _not_found(error: JsonRpcError) -> bool:
        return error.code == -32602 and "State not found" in error.message

    def append(self, state: State) -> None:
        self.client.call("state.append", state.model_dump(mode="json"))

    def get_by_id(self, state_id: UUID) -> State | None:
        try:
            value = self.client.call("state.get", {"state_id": str(state_id)})
        except JsonRpcError as exc:
            if self._not_found(exc):
                return None
            raise
        return self._state(value)

    def get_by_hash(self, state_hash: str) -> State | None:
        try:
            value = self.client.call("state.get_by_hash", {"hash": state_hash})
        except JsonRpcError as exc:
            if self._not_found(exc):
                return None
            raise
        return self._state(value)

    def list_states(self) -> list[State]:
        value = self.client.call("state.list", {"limit": 10_000})
        return [self._state(item) for item in value.get("states", [])]
