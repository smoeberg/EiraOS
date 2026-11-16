"""The gate's audit chain has its own database (UDVIKLINGSPLAN F1c.4,
vurderingen G-4).

identityd and delegationd write the app database (sessions, delegations), so
a chain kept there could be recomputed by them. The chain is now in
EIRA_GATE_AUDIT_DB (/data/eira-gate-audit.db), which only intentd's AppArmor
profile may write. An existing chain is moved unchanged at the first start.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

import pytest

from app.gate.store import GENESIS, AuditMigrationError, GateStore, audit_db_path

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "packaging" / "daemon-policy.json").read_text(encoding="utf-8"))
INSTALLED = "/data/eira-gate-audit.db"


def _tables(path) -> set[str]:
    with sqlite3.connect(path) as conn:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def _legacy_app_db(path: Path, entries: int) -> list[tuple]:
    """An app database as it was before F1c.4: the chain is a table in it."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE gate_audit (seq INTEGER PRIMARY KEY AUTOINCREMENT, entry TEXT NOT NULL,
                                 prev_hash TEXT NOT NULL, entry_hash TEXT NOT NULL);
        CREATE TRIGGER gate_audit_no_update BEFORE UPDATE ON gate_audit
            BEGIN SELECT RAISE(ABORT, 'gate_audit is append-only'); END;
        CREATE TRIGGER gate_audit_no_delete BEFORE DELETE ON gate_audit
            BEGIN SELECT RAISE(ABORT, 'gate_audit is append-only'); END;
    """)
    prev = GENESIS
    rows = []
    for n in range(entries):
        body = json.dumps({"step": "propose", "n": n}, sort_keys=True, separators=(",", ":"))
        entry_hash = "sha256:" + hashlib.sha256((prev + body).encode()).hexdigest()
        conn.execute("INSERT INTO gate_audit (entry, prev_hash, entry_hash) VALUES (?, ?, ?)",
                     (body, prev, entry_hash))
        rows.append((n + 1, body, prev, entry_hash))
        prev = entry_hash
    conn.commit()
    conn.close()
    return rows


def _chain(path) -> list[tuple]:
    with sqlite3.connect(path) as conn:
        return [tuple(r) for r in conn.execute(
            "SELECT seq, entry, prev_hash, entry_hash FROM gate_audit ORDER BY seq")]


def test_the_chain_is_not_in_the_app_database(tmp_path):
    store = GateStore(str(tmp_path / "eira-app.db"))
    store.append_audit({"step": "propose"})
    assert store.audit_path != store.db_path
    assert "gate_audit" not in _tables(store.db_path)
    assert len(_chain(store.audit_path)) == 1
    assert store.verify_audit_chain()


def test_the_installed_path_comes_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("EIRA_GATE_AUDIT_DB", str(tmp_path / "audit.db"))
    monkeypatch.setenv("EIRA_APP_DB", str(tmp_path / "eira-app.db"))
    assert audit_db_path() == str(tmp_path / "audit.db")
    # An explicit app database (tests, eira-audit-verify --db) gets its own.
    assert audit_db_path(str(tmp_path / "copy.db")) == str(tmp_path / "copy-gate-audit.db")


def test_an_old_chain_is_moved_unchanged(tmp_path):
    app = tmp_path / "eira-app.db"
    old = _legacy_app_db(app, 5)
    store = GateStore(str(app))
    assert _chain(store.audit_path) == old  # positions and hashes, as the anchors name them
    assert "gate_audit" not in _tables(app)
    assert store.verify_audit_chain()
    assert store.audit_head() == (5, old[-1][3])
    store.append_audit({"step": "after"})
    assert store.verify_audit_chain() and store.audit_head()[0] == 6


def test_a_crash_after_the_copy_is_finished_on_the_next_start(tmp_path):
    app = tmp_path / "eira-app.db"
    old = _legacy_app_db(app, 3)
    store = GateStore(str(app))
    store.append_audit({"step": "after"})
    # As if the drop had not happened: the old table is back, a prefix.
    _legacy_app_db(app, 3)
    GateStore(str(app))
    assert "gate_audit" not in _tables(app)
    assert _chain(store.audit_path)[:3] == old and len(_chain(store.audit_path)) == 4


def test_two_chains_that_disagree_stop_the_gate(tmp_path):
    app = tmp_path / "eira-app.db"
    store = GateStore(str(app))
    store.append_audit({"step": "a different history"})
    _legacy_app_db(app, 2)
    with pytest.raises(AuditMigrationError):
        GateStore(str(app))
    assert len(_chain(app)) == 2  # nothing is dropped


def test_the_audit_database_is_still_append_only(tmp_path):
    store = GateStore(str(tmp_path / "eira-app.db"))
    store.append_audit({"step": "propose"})
    with sqlite3.connect(store.audit_path) as conn:
        for statement in ("UPDATE gate_audit SET entry = '{}'", "DELETE FROM gate_audit"):
            with pytest.raises(sqlite3.DatabaseError):
                conn.execute(statement)


# --- only intentd may write it ---------------------------------------------------------


AUDIT_RULE = re.compile(r"^\s*/data/eira-gate-audit\.db(\S*)\s+(\w+),", re.M)


def test_only_intentd_s_profile_names_the_audit_database():
    profiles = sorted((ROOT / "packaging").rglob("usr.*eira*"))
    assert profiles
    for profile in profiles:
        text = profile.read_text(encoding="utf-8")
        rules = AUDIT_RULE.findall(text)
        if profile.name == "usr.bin.eira-intentd":
            assert ("", "rwk") in rules and ("-{journal,shm,wal}", "rwk") in rules
        else:
            assert rules == [] and "eira-gate-audit" not in text, profile.name


def test_the_installed_units_and_the_verifier_use_the_same_file():
    unit = (ROOT / "systemd" / "eira-intentd.service").read_text(encoding="utf-8")
    assert f"Environment=EIRA_GATE_AUDIT_DB={INSTALLED}" in unit
    verify = (ROOT / "packaging" / "bin" / "eira-audit-verify").read_text(encoding="utf-8")
    assert f"EIRA_GATE_AUDIT_DB=${{EIRA_GATE_AUDIT_DB:-{INSTALLED}}}" in verify
    for daemon in POLICY["production_daemons"]:
        if daemon != "intentd":
            text = (ROOT / "systemd" / f"eira-{daemon}.service").read_text(encoding="utf-8")
            assert "EIRA_GATE_AUDIT_DB" not in text, daemon
