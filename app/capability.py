from __future__ import annotations

import json
from pathlib import Path

from app.database import get_connection, utc_now_iso
from app.models import (
    CapabilityManifest,
)

MANIFESTS_DIR = Path(__file__).resolve().parent.parent / "manifests"


def seed_capabilities() -> None:
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM capability_manifests").fetchone()["c"]
        if count > 0:
            return

    now = utc_now_iso()
    for path in sorted(MANIFESTS_DIR.glob("*.capability.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        manifest = CapabilityManifest.model_validate(data)
        conn_data = (
            manifest.adapter_id,
            manifest.name,
            manifest.version,
            manifest.conformance,
            manifest.model_dump_json(),
            now,
            now,
        )
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO capability_manifests
                (adapter_id, name, version, conformance, manifest_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                conn_data,
            )


def list_manifests() -> list[CapabilityManifest]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT manifest_json FROM capability_manifests ORDER BY name ASC"
        ).fetchall()
    return [CapabilityManifest.model_validate_json(row["manifest_json"]) for row in rows]


def get_manifest(adapter_id: str) -> CapabilityManifest | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT manifest_json FROM capability_manifests WHERE adapter_id = ?",
            (adapter_id,),
        ).fetchone()
    if not row:
        return None
    return CapabilityManifest.model_validate_json(row["manifest_json"])


def seed_adapter_health() -> None:
    now = utc_now_iso()
    with get_connection() as conn:
        for manifest in list_manifests():
            conn.execute(
                """
                INSERT INTO adapter_health (adapter_id, status, last_seen)
                VALUES (?, 'online', ?)
                ON CONFLICT(adapter_id) DO UPDATE SET
                  status = 'online', last_seen = excluded.last_seen
                """,
                (manifest.adapter_id, now),
            )


def is_adapter_online(adapter_id: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT status FROM adapter_health WHERE adapter_id = ?",
            (adapter_id,),
        ).fetchone()
    if not row:
        return False
    return row["status"] == "online"
