from __future__ import annotations

import json
import sqlite3
import threading
from typing import List, Optional
from uuid import UUID

from app.core.state import State


class StateStore:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._shared_conn: Optional[sqlite3.Connection] = None
        if db_path == ":memory:":
            self._shared_conn = self._configure_conn(
                sqlite3.connect(":memory:", check_same_thread=False)
            )
        self._init_db()

    def _configure_conn(self, conn: sqlite3.Connection) -> sqlite3.Connection:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA foreign_keys = ON")
        if self.db_path != ":memory:":
            conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def _get_conn(self) -> sqlite3.Connection:
        if self._shared_conn:
            return self._shared_conn
        return self._configure_conn(sqlite3.connect(self.db_path, timeout=5.0))

    def _init_db(self) -> None:
        conn = self._get_conn()
        if not self._shared_conn:
            conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS states (
                id TEXT PRIMARY KEY,
                version INTEGER NOT NULL,
                timestamp_ns INTEGER NOT NULL,
                type TEXT NOT NULL,
                payload TEXT NOT NULL,
                previous_state_id TEXT,
                hash TEXT UNIQUE NOT NULL
            )
            """
        )
        conn.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS states_append_only_update
            BEFORE UPDATE ON states
            BEGIN
                SELECT RAISE(ABORT, 'states are append-only');
            END;

            CREATE TRIGGER IF NOT EXISTS states_append_only_delete
            BEFORE DELETE ON states
            BEGIN
                SELECT RAISE(ABORT, 'states are append-only');
            END;
            """
        )
        if not self._shared_conn:
            conn.commit()
            conn.close()

    def append(self, state: State) -> None:
        if not state.is_hash_valid():
            raise ValueError("State hash does not match canonical state content")
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO states
                (id, version, timestamp_ns, type, payload, previous_state_id, hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(state.id),
                    state.version,
                    state.timestamp_ns,
                    state.type,
                    json.dumps(
                        state.payload,
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                        allow_nan=False,
                    ),
                    str(state.previous_state_id) if state.previous_state_id else None,
                    state.hash,
                ),
            )
            conn.commit()
            if not self._shared_conn:
                conn.close()

    @staticmethod
    def _row_to_state(row: sqlite3.Row) -> State:
        return State(
            id=UUID(row["id"]),
            version=row["version"],
            timestamp_ns=row["timestamp_ns"],
            type=row["type"],
            payload=json.loads(row["payload"]),
            previous_state_id=(
                UUID(row["previous_state_id"]) if row["previous_state_id"] else None
            ),
            hash=row["hash"],
        )

    def get_by_id(self, state_id: UUID) -> Optional[State]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM states WHERE id = ?", (str(state_id),)
        ).fetchone()
        if not self._shared_conn:
            conn.close()
        if not row:
            return None
        return self._row_to_state(row)

    def get_by_hash(self, state_hash: str) -> Optional[State]:
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM states WHERE hash = ?", (state_hash,)
            ).fetchone()
            if not self._shared_conn:
                conn.close()
        return self._row_to_state(row) if row else None

    def list_states(self) -> List[State]:
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT * FROM states ORDER BY timestamp_ns, id"
            ).fetchall()
            if not self._shared_conn:
                conn.close()
        return [self._row_to_state(row) for row in rows]

    def get_history(self, latest_state_id: UUID) -> List[State]:
        history = []
        curr_id = latest_state_id
        while curr_id:
            state = self.get_by_id(curr_id)
            if not state:
                break
            history.append(state)
            curr_id = state.previous_state_id
        return history

    def count(self) -> int:
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) AS count FROM states").fetchone()
        if not self._shared_conn:
            conn.close()
        return int(row["count"])
