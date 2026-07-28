from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "eira.db"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS objects (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                name TEXT NOT NULL,
                owner_id TEXT,
                metadata TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS relations (
                id TEXT PRIMARY KEY,
                from_id TEXT NOT NULL,
                to_id TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                weight REAL DEFAULT 1.0,
                valid_from TEXT NOT NULL,
                valid_to TEXT,
                evidence TEXT NOT NULL DEFAULT '{}',
                metadata TEXT DEFAULT '{}',
                FOREIGN KEY (from_id) REFERENCES objects(id),
                FOREIGN KEY (to_id) REFERENCES objects(id)
            );

            CREATE INDEX IF NOT EXISTS idx_relations_temporal
                ON relations(from_id, to_id, relation_type, valid_from, valid_to);

            CREATE TABLE IF NOT EXISTS trust_items (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                trust_score INTEGER NOT NULL,
                trust_level TEXT NOT NULL,
                sources TEXT DEFAULT '[]',
                object_id TEXT,
                sort_order INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS journeys (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                total_steps INTEGER NOT NULL,
                current_step INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS journey_steps (
                id TEXT PRIMARY KEY,
                journey_id TEXT NOT NULL,
                step_order INTEGER NOT NULL,
                label TEXT NOT NULL,
                actor_name TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                completed_at TEXT,
                FOREIGN KEY (journey_id) REFERENCES journeys(id)
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS capability_manifests (
                adapter_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                version TEXT NOT NULL,
                conformance TEXT NOT NULL DEFAULT 'CORE',
                manifest_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                actor_id TEXT NOT NULL,
                actor_name TEXT NOT NULL,
                org_unit TEXT NOT NULL,
                assurance_level TEXT NOT NULL DEFAULT 'eid_low',
                delegated_for TEXT,
                presentation_mode TEXT NOT NULL DEFAULT 'explorer',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pending_intents (
                intent_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending_confirmation',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );

            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                hostname TEXT,
                tenant_id TEXT,
                bundle_applied TEXT,
                bundle_pending TEXT,
                compliance_pct INTEGER DEFAULT 100,
                last_heartbeat TEXT,
                enrolled_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active'
            );

            CREATE TABLE IF NOT EXISTS adapter_health (
                adapter_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'offline',
                last_seen TEXT,
                FOREIGN KEY (adapter_id) REFERENCES capability_manifests(adapter_id)
            );
            """
        )
        _migrate_v03(conn)
        _migrate_p0(conn)
        _migrate_oidc(conn)


def _migrate_p0(conn: sqlite3.Connection) -> None:
    """Idempotent migrations for scope-closure P0 tables."""
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "sessions" not in tables:
        conn.executescript(
            """
            CREATE TABLE sessions (
                session_id TEXT PRIMARY KEY,
                actor_id TEXT NOT NULL,
                actor_name TEXT NOT NULL,
                org_unit TEXT NOT NULL,
                assurance_level TEXT NOT NULL DEFAULT 'eid_low',
                delegated_for TEXT,
                presentation_mode TEXT NOT NULL DEFAULT 'explorer',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE pending_intents (
                intent_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending_confirmation',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE devices (
                device_id TEXT PRIMARY KEY,
                hostname TEXT,
                tenant_id TEXT,
                bundle_applied TEXT,
                bundle_pending TEXT,
                compliance_pct INTEGER DEFAULT 100,
                last_heartbeat TEXT,
                enrolled_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active'
            );
            CREATE TABLE adapter_health (
                adapter_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'offline',
                last_seen TEXT
            );
            """
        )


def _migrate_oidc(conn: sqlite3.Connection) -> None:
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "oidc_auth_states" not in tables:
        conn.execute(
            """
            CREATE TABLE oidc_auth_states (
                state TEXT PRIMARY KEY,
                code_verifier TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def _migrate_v03(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(relations)").fetchall()}
    if "evidence" not in cols:
        conn.execute(
            "ALTER TABLE relations ADD COLUMN evidence TEXT NOT NULL DEFAULT '{}'"
        )


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
