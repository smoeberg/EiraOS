from __future__ import annotations

import uuid

from app.database import get_connection, utc_now_iso
from app.ipc.jsonrpc import JsonRpcError


def fleet_enroll(params: dict) -> dict:
    device_id = params.get("device_id") or str(uuid.uuid4())
    hostname = params.get("hostname", "unknown")
    tenant_id = params.get("tenant_id", "default")
    now = utc_now_iso()

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO devices
            (device_id, hostname, tenant_id, bundle_applied, bundle_pending,
             compliance_pct, last_heartbeat, enrolled_at, status)
            VALUES (?, ?, ?, NULL, NULL, 100, ?, ?, 'active')
            ON CONFLICT(device_id) DO UPDATE SET
              hostname = excluded.hostname,
              last_heartbeat = excluded.last_heartbeat,
              status = 'active'
            """,
            (device_id, hostname, tenant_id, now, now),
        )

    return {
        "device_id": device_id,
        "status": "enrolled",
        "enrolled_at": now,
    }


def fleet_heartbeat(params: dict) -> dict:
    device_id = params.get("device_id")
    if not device_id:
        raise JsonRpcError(-32602, "device_id required")

    bundle_applied = params.get("bundle_applied")
    compliance_pct = params.get("compliance_pct", 100)
    now = utc_now_iso()

    with get_connection() as conn:
        row = conn.execute(
            "SELECT device_id FROM devices WHERE device_id = ?", (device_id,)
        ).fetchone()
        if not row:
            raise JsonRpcError(-32602, "device not enrolled", {"device_id": device_id})

        if bundle_applied:
            conn.execute(
                """
                UPDATE devices SET last_heartbeat = ?, bundle_applied = ?,
                compliance_pct = ?, status = 'active'
                WHERE device_id = ?
                """,
                (now, bundle_applied, compliance_pct, device_id),
            )
        else:
            conn.execute(
                """
                UPDATE devices SET last_heartbeat = ?, compliance_pct = ?
                WHERE device_id = ?
                """,
                (now, compliance_pct, device_id),
            )

    return {
        "device_id": device_id,
        "ack": True,
        "server_time": now,
        "commands": [],
    }


def fleet_device_get(params: dict) -> dict:
    device_id = params.get("device_id")
    if not device_id:
        raise JsonRpcError(-32602, "device_id required")

    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM devices WHERE device_id = ?", (device_id,)
        ).fetchone()
    if not row:
        raise JsonRpcError(-32602, "device not found")

    return dict(row)


def fleet_list(params: dict) -> list:
    limit = int(params.get("limit", 50))
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM devices ORDER BY last_heartbeat DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def register_fleet_handlers(server) -> None:
    server.register("fleet.enroll", fleet_enroll)
    server.register("fleet.heartbeat", fleet_heartbeat)
    server.register("fleet.device.get", fleet_device_get)
    server.register("fleet.list", fleet_list)
    server.register("health", lambda _: {"daemon": "eira-fleetd", "ok": True})
