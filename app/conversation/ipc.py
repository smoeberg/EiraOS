"""Hændelsesstrømmen over intentd's socket (EIRA-CONVERSATION-1.0 §5).

Alle metoder er læsninger. De kræver et menneske i en autentificeret session,
der er bundet til kalderens UID (samme regel som gatens samtykke). Modellen kan
ikke læse strømmen, før "på vegne af"-delegationen findes (GATE-KERNEL bilag A
pkt. 1). En samtale, man ikke kan se, giver samme svar som en, der ikke findes.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import Any

from app.conversation import feed
from app.gate.caller import Caller, acting_as, from_peer
from app.gate.kernel import Gate
from app.ipc.auth import PEER_KEY
from app.ipc.jsonrpc import JsonRpcError

NO_SESSION = -32041
UNKNOWN_CONVERSATION = -32042

METHODS = (
    "events.since",
    "conversation.list",
    "conversation.events",
    "conversation.members",
    "conversation.awaiting",
)


def _int(params: dict[str, Any], name: str, default: int) -> int:
    value = params.get(name, default)
    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise JsonRpcError(-32602, f"{name} must be a non-negative integer")
    return value


def _conversation_id(params: dict[str, Any]) -> str:
    value = params.get("conversation_id")
    if not isinstance(value, str) or not value:
        raise JsonRpcError(-32602, "conversation_id is required")
    return value


def register_conversation_handlers(server, gate: Gate) -> None:
    def connect() -> sqlite3.Connection:
        conn = sqlite3.connect(gate.store.db_path, timeout=10)
        feed.ensure_schema(conn)
        return conn

    def reader(handler):
        def wrapped(params: dict[str, Any]) -> dict[str, Any]:
            caller: Caller | None = from_peer(params.pop(PEER_KEY, None))
            with acting_as(caller):
                actor = gate._human_actor(params.get("session_id"))
            if actor is None:
                raise JsonRpcError(NO_SESSION, "E_NO_SESSION", {"user_message": "Log ind for at se samtalerne."})
            return handler(params, actor["identity"])

        wrapped.wants_peer = True
        return wrapped

    def since(params: dict[str, Any], identity: str) -> dict[str, Any]:
        cursor = _int(params, "cursor", 0)
        limit = _int(params, "limit", 50)
        wait_ms = _int(params, "wait_ms", 0)
        with closing(connect()) as conn:
            page = feed.since(conn, identity, cursor, limit)
        if page["events"] or not wait_ms:
            return page
        # Long-poll (§5.2): wait for anything new, then answer once. A wake-up
        # for an event the identity cannot see returns an empty page with a
        # moved cursor, never the event.
        feed.NOTIFIER.wait_beyond(page["cursor"], wait_ms / 1000)
        with closing(connect()) as conn:
            return feed.since(conn, identity, page["cursor"], limit)

    def conversations(_params: dict[str, Any], identity: str) -> dict[str, Any]:
        with closing(connect()) as conn:
            return {"conversations": feed.conversations(conn, identity)}

    def events(params: dict[str, Any], identity: str) -> dict[str, Any]:
        conversation = _conversation_id(params)
        before = params.get("before")
        if before is not None:
            before = _int(params, "before", 0)
        with closing(connect()) as conn:
            found = feed.history(conn, identity, conversation, before, _int(params, "limit", 50))
        if found is None:
            raise JsonRpcError(UNKNOWN_CONVERSATION, "unknown conversation")
        return {"conversation_id": conversation, "events": found}

    def members(params: dict[str, Any], identity: str) -> dict[str, Any]:
        conversation = _conversation_id(params)
        with closing(connect()) as conn:
            found = feed.members(conn, identity, conversation)
        if found is None:
            raise JsonRpcError(UNKNOWN_CONVERSATION, "unknown conversation")
        return {"conversation_id": conversation, "members": found}

    def awaiting(_params: dict[str, Any], identity: str) -> dict[str, Any]:
        with closing(connect()) as conn:
            return feed.awaiting(conn, identity)

    server.register("events.since", reader(since))
    server.register("conversation.list", reader(conversations))
    server.register("conversation.events", reader(events))
    server.register("conversation.members", reader(members))
    server.register("conversation.awaiting", reader(awaiting))
