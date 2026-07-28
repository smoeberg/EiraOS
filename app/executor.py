from __future__ import annotations

import json
import uuid

from app.capability import is_adapter_online
from app.database import get_connection, utc_now_iso
from app.ipc.jsonrpc import JsonRpcError


def execute_intent(pending: dict) -> dict:
    match = pending.get("capability_match")
    if not match:
        raise JsonRpcError(
            -32002,
            "cannot_execute",
            {"user_message": "Ingen capability match — kan ikke udføre"},
        )

    adapter_id = match["adapter_id"]
    if not is_adapter_online(adapter_id):
        raise JsonRpcError(
            -32014,
            "capability_unavailable",
            {
                "user_message": f"Adapter {adapter_id} er ikke tilgængelig",
                "adapter_id": adapter_id,
            },
        )

    action = pending.get("action", "")
    execution_id = str(uuid.uuid4())
    snapshot_required = action in ("apply_bundle", "approve_bundle")

    result = {
        "execution_id": execution_id,
        "intent_id": pending.get("intent_id"),
        "adapter_id": adapter_id,
        "action": action,
        "resource": pending.get("resource", "document"),
        "status": "executed_stub",
        "message": (
            f"Handling '{action}' sendt til {match.get('adapter_name', adapter_id)} "
            "(prototype — ingen ekstern API)"
        ),
        "snapshot_required": snapshot_required,
        "snapshot_note": (
            "Ved produktion: btrfs/zfs snapshot før bundle apply (governance-agent)"
            if snapshot_required
            else None
        ),
    }

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO audit_events (id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                "capability.executed",
                json.dumps(result),
                utc_now_iso(),
            ),
        )

    return result
