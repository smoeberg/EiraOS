"""Gate-tilstand i SQLite: handlinger, samtykker, rettigheder og audit.

Audit-tabellen er append-only (triggers afviser UPDATE og DELETE) og
hash-kædet, så en ændring af en tidligere post kan opdages. Modeller og
adaptere har ingen skriveadgang til den; kun :class:`Gate` skriver.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from app.session_store import get_db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS gate_actions (
    action_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    origin TEXT NOT NULL,
    session_id TEXT NOT NULL,
    actor_identity TEXT NOT NULL,
    raw TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    policy_fingerprint TEXT NOT NULL,
    state TEXT NOT NULL,
    execution_id TEXT,
    result TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    rendering_text TEXT,
    rendering_hash TEXT,
    renderer_version TEXT,
    render_lang TEXT
);
CREATE TABLE IF NOT EXISTS gate_consents (
    consent_id TEXT PRIMARY KEY,
    action_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    rendering_hash TEXT,
    session_id TEXT NOT NULL,
    granted_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE TABLE IF NOT EXISTS gate_identities (
    actor_id TEXT PRIMARY KEY,
    identity TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS gate_members (
    conversation_id TEXT NOT NULL,
    identity TEXT NOT NULL,
    PRIMARY KEY (conversation_id, identity)
);
CREATE TABLE IF NOT EXISTS gate_audit (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    entry TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    entry_hash TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS gate_audit_no_update
    BEFORE UPDATE ON gate_audit
    BEGIN SELECT RAISE(ABORT, 'gate_audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS gate_audit_no_delete
    BEFORE DELETE ON gate_audit
    BEGIN SELECT RAISE(ABORT, 'gate_audit is append-only'); END;
"""

GENESIS = "sha256:" + "0" * 64

# Columns added after Gate Kernel 1.0 shipped (renderer binding).
MIGRATIONS = {
    "gate_actions": {
        "rendering_text": "TEXT",
        "rendering_hash": "TEXT",
        "renderer_version": "TEXT",
        "render_lang": "TEXT",
    },
    "gate_consents": {"rendering_hash": "TEXT", "boot_id": "TEXT", "boottime_ns": "INTEGER"},
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


class GateStore:
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or get_db_path()
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            for table, columns in MIGRATIONS.items():
                existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
                for name, kind in columns.items():
                    if name not in existing:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # --- actions -----------------------------------------------------------

    def find(self, action_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM gate_actions WHERE action_id = ?", (action_id,)).fetchone()
        return dict(row) if row else None

    def insert_pending(self, record: dict[str, Any]) -> bool:
        """Insert a new pending action. False if the id already exists."""
        now = iso(utc_now())
        with self._connect() as conn:
            try:
                conn.execute(
                    """INSERT INTO gate_actions (action_id, conversation_id, action_type, origin,
                       session_id, actor_identity, raw, content_hash, policy_version,
                       policy_fingerprint, state, created_at, updated_at, rendering_text,
                       rendering_hash, renderer_version, render_lang)
                       VALUES (:action_id, :conversation_id, :action_type, :origin, :session_id,
                       :actor_identity, :raw, :content_hash, :policy_version,
                       :policy_fingerprint, 'pending', :now, :now, :rendering_text,
                       :rendering_hash, :renderer_version, :render_lang)""",
                    {**record, "now": now},
                )
            except sqlite3.IntegrityError:
                return False
        return True

    def claim(self, action_id: str, content_hash: str) -> str | None:
        """Atomically move pending → executing. Returns the new execution id,
        or None if another caller claimed it first or the binding differs."""
        execution_id = str(uuid.uuid4())
        with self._connect() as conn:
            cursor = conn.execute(
                """UPDATE gate_actions SET state = 'executing', execution_id = ?, updated_at = ?
                   WHERE action_id = ? AND state = 'pending' AND content_hash = ?""",
                (execution_id, iso(utc_now()), action_id, content_hash),
            )
        return execution_id if cursor.rowcount == 1 else None

    def executing(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM gate_actions WHERE state = 'executing'").fetchall()
        return [dict(r) for r in rows]

    def release(self, action_id: str, execution_id: str) -> None:
        """Undo a claim when the gate rejects after claiming (no side effect yet)."""
        with self._connect() as conn:
            conn.execute(
                """UPDATE gate_actions SET state = 'pending', execution_id = NULL, updated_at = ?
                   WHERE action_id = ? AND execution_id = ? AND state = 'executing'""",
                (iso(utc_now()), action_id, execution_id),
            )

    def finish(self, action_id: str, execution_id: str, state: str, result: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """UPDATE gate_actions SET state = ?, result = ?, updated_at = ?
                   WHERE action_id = ? AND execution_id = ?""",
                (state, json.dumps(result, sort_keys=True), iso(utc_now()), action_id, execution_id),
            )

    def cancel(self, action_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE gate_actions SET state = 'cancelled', updated_at = ? WHERE action_id = ? AND state = 'pending'",
                (iso(utc_now()), action_id),
            )
        return cursor.rowcount == 1

    # --- consent -----------------------------------------------------------

    def grant_consent(
        self,
        action_id: str,
        content_hash: str,
        rendering_hash: str | None,
        session_id: str,
        expires_at: datetime,
        boot_id: str | None = None,
        boottime_ns: int | None = None,
    ) -> str:
        """``expires_at`` is wall-clock time for display and audit only;
        validity is decided on (boot_id, boottime_ns). A row without them is
        never valid (fail closed, e.g. rows from before the migration)."""
        consent_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO gate_consents (consent_id, action_id, content_hash, rendering_hash,
                   session_id, granted_at, expires_at, boot_id, boottime_ns)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    consent_id,
                    action_id,
                    content_hash,
                    rendering_hash,
                    session_id,
                    iso(utc_now()),
                    iso(expires_at),
                    boot_id,
                    boottime_ns,
                ),
            )
        return consent_id

    def consents_for(self, action_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM gate_consents WHERE action_id = ?", (action_id,)).fetchall()
        return [dict(r) for r in rows]

    # --- identities, membership, rights ------------------------------------

    def bind_identity(self, actor_id: str, identity: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO gate_identities (actor_id, identity) VALUES (?, ?) "
                "ON CONFLICT(actor_id) DO UPDATE SET identity = excluded.identity",
                (actor_id, identity),
            )

    def identity_for(self, actor_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT identity FROM gate_identities WHERE actor_id = ?", (actor_id,)
            ).fetchone()
        return row["identity"] if row else None

    def add_member(self, conversation_id: str, identity: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO gate_members (conversation_id, identity) VALUES (?, ?)",
                (conversation_id, identity),
            )

    def is_member(self, conversation_id: str, identity: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM gate_members WHERE conversation_id = ? AND identity = ?",
                (conversation_id, identity),
            ).fetchone()
        return row is not None

    # --- audit -------------------------------------------------------------

    def append_audit(self, entry: dict[str, Any]) -> str:
        body = json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute("SELECT entry_hash FROM gate_audit ORDER BY seq DESC LIMIT 1").fetchone()
                prev = row["entry_hash"] if row else GENESIS
                entry_hash = "sha256:" + hashlib.sha256((prev + body).encode()).hexdigest()
                conn.execute(
                    "INSERT INTO gate_audit (entry, prev_hash, entry_hash) VALUES (?, ?, ?)",
                    (body, prev, entry_hash),
                )
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        return entry_hash

    def audit_entries(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM gate_audit ORDER BY seq").fetchall()
        return [dict(r) for r in rows]

    def verify_audit_chain(self) -> bool:
        prev = GENESIS
        for row in self.audit_entries():
            expected = "sha256:" + hashlib.sha256((prev + row["entry"]).encode()).hexdigest()
            if row["prev_hash"] != prev or row["entry_hash"] != expected:
                return False
            prev = row["entry_hash"]
        return True
