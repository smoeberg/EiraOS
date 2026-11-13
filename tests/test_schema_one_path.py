"""One way to the database schema (UDVIKLINGSPLAN F1.10, fundregister S-21, D-12).

The module that owns a table creates and upgrades it when it opens the
database (docs/reference/databaseskema.md). There is no Alembic: it knew two
of the tables, and running it first in CI gave audit_events another shape
than on an installed machine.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_there_is_no_second_schema_path():
    assert not (ROOT / "alembic").exists()
    assert not (ROOT / "alembic.ini").exists()
    for path in (
        ROOT / ".github" / "workflows" / "ci.yml",
        ROOT / "packaging" / "debian" / "rules",
        ROOT / "README.md",
        ROOT / "requirements.txt",
        ROOT / "requirements-dev.txt",
    ):
        assert "alembic" not in path.read_text(encoding="utf-8").lower(), path.name


def test_the_rule_is_written_down():
    doc = (ROOT / "docs" / "reference" / "databaseskema.md").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS" in doc and "ADD COLUMN" in doc


def _schema(path: Path) -> dict[str, list[tuple]]:
    with sqlite3.connect(path) as conn:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        return {t: [tuple(c) for c in conn.execute(f"PRAGMA table_info({t})")] for t in tables}


def _init(path: Path, monkeypatch) -> None:
    from app import database, session_store

    monkeypatch.setenv("EIRA_DB_PATH", str(path))
    monkeypatch.setattr(database, "DB_PATH", path)
    database.init_db()
    session_store.init_db()


def test_initialisation_is_idempotent(tmp_path, monkeypatch):
    path = tmp_path / "app.db"
    _init(path, monkeypatch)
    first = _schema(path)
    _init(path, monkeypatch)
    assert _schema(path) == first


def test_an_old_database_is_upgraded_to_the_same_shape_as_a_new_one(tmp_path, monkeypatch):
    fresh = tmp_path / "fresh.db"
    _init(fresh, monkeypatch)

    old = tmp_path / "old.db"
    with sqlite3.connect(old) as conn:
        # The sessions table before Bilag A pkt. 1, with a consent key on disk.
        conn.execute(
            "CREATE TABLE sessions (session_id TEXT PRIMARY KEY, actor_id TEXT, actor_name TEXT,"
            " org_unit TEXT, assurance_level TEXT, delegated_for TEXT, presentation_mode TEXT,"
            " created_at TEXT, updated_at TEXT)"
        )
        conn.execute("INSERT INTO sessions (session_id, actor_id) VALUES ('s-old', 'anne')")
    _init(old, monkeypatch)

    upgraded, new = _schema(old), _schema(fresh)
    assert {c[1] for c in upgraded["sessions"]} == {c[1] for c in new["sessions"]}
    assert set(upgraded) == set(new)
    with sqlite3.connect(old) as conn:
        assert conn.execute("SELECT actor_id FROM sessions WHERE session_id = 's-old'").fetchone() == ("anne",)
