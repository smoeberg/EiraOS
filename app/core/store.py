from __future__ import annotations

import sqlite3
import json
from uuid import UUID
from typing import Optional, List
from app.core.state import State


class StateStore:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS states (
                    id TEXT PRIMARY KEY,
                    version INTEGER NOT NULL,
                    timestamp_ns INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    previous_state_id TEXT,
                    hash TEXT UNIQUE NOT NULL
                )
            """)

    def append(self, state: State) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO states (id, version, timestamp_ns, type, payload, previous_state_id, hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(state.id),
                    state.version,
                    state.timestamp_ns,
                    state.type,
                    json.dumps(state.payload),
                    str(state.previous_state_id) if state.previous_state_id else None,
                    state.hash
                )
            )

    def get_by_id(self, state_id: UUID) -> Optional[State]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM states WHERE id = ?", (str(state_id),)).fetchone()
            if not row:
                return None
            return State(
                id=UUID(row["id"]),
                version=row["version"],
                timestamp_ns=row["timestamp_ns"],
                type=row["type"],
                payload=json.loads(row["payload"]),
                previous_state_id=UUID(row["previous_state_id"]) if row["previous_state_id"] else None,
                hash=row["hash"]
            )

    def get_history(self, latest_state_id: UUID) -> List[State]:
        history = []
        curr_id = latest_state_id
        while curr_id:
            st = self.get_by_id(curr_id)
            if not st:
                break
            history.append(st)
            curr_id = st.previous_state_id
        return history
