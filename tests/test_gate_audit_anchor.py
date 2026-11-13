"""External anchors for the audit chain (GATE-KERNEL bilag A pkt. 2)."""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3

import pytest

from app.gate import audit_anchor, audit_verify
from app.gate.store import GENESIS, GateStore


@pytest.fixture
def store(tmp_path):
    s = GateStore(str(tmp_path / "gate.db"))
    for i in range(5):
        s.append_audit({"step": "propose", "n": i})
    return s


def rewrite_whole_chain(db_path, change):
    """What root, or a compromised writer, can do: drop the append-only
    triggers, change history and recompute every hash so the chain is
    internally valid again."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("DROP TRIGGER gate_audit_no_update")
    conn.execute("DROP TRIGGER gate_audit_no_delete")
    rows = [dict(r) for r in conn.execute("SELECT * FROM gate_audit ORDER BY seq")]
    rows = change(rows)
    conn.execute("DELETE FROM gate_audit")
    prev = GENESIS
    for row in rows:
        entry_hash = "sha256:" + hashlib.sha256((prev + row["entry"]).encode()).hexdigest()
        conn.execute("INSERT INTO gate_audit (entry, prev_hash, entry_hash) VALUES (?, ?, ?)",
                     (row["entry"], prev, entry_hash))
        prev = entry_hash
    conn.commit()
    conn.close()


def test_emit_writes_journal_line_and_file(store, tmp_path):
    out = io.StringIO()
    anchor = audit_anchor.emit(store, out=out, path=tmp_path / "audit" / "anchor.json")
    assert anchor.seq == 5 and anchor.head.startswith("sha256:")
    assert audit_anchor.parse_journal(out.getvalue().splitlines()) == [
        audit_anchor.Anchor(5, anchor.head, anchor.at)
    ]
    assert json.loads((tmp_path / "audit" / "anchor.json").read_text())["head"] == anchor.head


def test_malformed_journal_lines_are_never_anchors():
    lines = ["noise", "EIRA_AUDIT_ANCHOR {bad json", 'EIRA_AUDIT_ANCHOR {"seq": "x"}',
             'prefix EIRA_AUDIT_ANCHOR {"seq": 1, "head": "sha256:aa"}']
    assert audit_anchor.parse_journal(lines) == [audit_anchor.Anchor(1, "sha256:aa", None)]


def test_untouched_chain_agrees_with_its_anchors(store):
    early = audit_anchor.current(store)
    store.append_audit({"step": "confirm"})
    late = audit_anchor.current(store)
    verdict = audit_anchor.verify(store, [early, late, audit_anchor.Anchor(0, GENESIS)])
    assert verdict == audit_anchor.Verdict(True, 3)


def test_whole_chain_rewrite_is_caught_by_an_anchor(store, tmp_path):
    anchor = audit_anchor.current(store)

    def change(rows):
        rows[1]["entry"] = json.dumps({"step": "propose", "n": 1, "erased": True})
        return rows

    rewrite_whole_chain(store.db_path, change)
    assert store.verify_audit_chain()  # internally perfect again …
    verdict = audit_anchor.verify(store, [anchor])  # … but not what was anchored
    assert (verdict.ok, verdict.problem) == (False, "head_mismatch:seq=5")


def test_truncation_is_caught(store):
    anchor = audit_anchor.current(store)
    rewrite_whole_chain(store.db_path, lambda rows: rows[:3])
    verdict = audit_anchor.verify(store, [anchor])
    assert (verdict.ok, verdict.problem) == (False, "chain_shorter_than_anchor:seq=5")


def test_renumbered_seq_column_does_not_matter(store):
    anchor = audit_anchor.current(store)
    conn = sqlite3.connect(store.db_path)
    conn.execute("DROP TRIGGER gate_audit_no_update")
    conn.execute("UPDATE gate_audit SET seq = seq + 1000")
    conn.commit()
    conn.close()
    assert audit_anchor.verify(store, [anchor]).ok  # position, not the column, is anchored


def test_a_broken_chain_fails_before_any_anchor(store):
    conn = sqlite3.connect(store.db_path)
    conn.execute("DROP TRIGGER gate_audit_no_update")
    conn.execute("UPDATE gate_audit SET entry = '{}' WHERE seq = 2")
    conn.commit()
    conn.close()
    assert audit_anchor.verify(store, []).problem == "chain_broken"


# --- eira-audit-verify ------------------------------------------------------------------


def test_cli_with_fleet_export(store, tmp_path, capsys):
    export = tmp_path / "fleet-anchors.json"
    export.write_text(json.dumps([audit_anchor.current(store).to_json()]))
    assert audit_verify.main(["--anchors", str(export), "--db", store.db_path]) == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "anchors": 1, "problem": None}
    rewrite_whole_chain(store.db_path, lambda rows: rows[:-1] + [{"entry": "{}"}])
    assert audit_verify.main(["--anchors", str(export), "--db", store.db_path]) == 1


def test_cli_without_anchors_is_not_a_pass(store, capsys):
    assert audit_verify.main(["--db", store.db_path]) == 2
    assert json.loads(capsys.readouterr().out)["problem"] == "no_anchors"


def test_cli_reads_the_journal(store, monkeypatch, capsys):
    anchor = audit_anchor.current(store)

    class Result:
        stdout = "start\n" + audit_anchor.PREFIX + json.dumps(anchor.to_json()) + "\n"
        returncode = 0

    monkeypatch.setattr(audit_verify.subprocess, "run", lambda *a, **k: Result())
    assert audit_verify.main(["--journal", "--db", store.db_path]) == 0


def test_failed_journal_seal_stops_verification(store, monkeypatch, capsys):
    class Result:
        stdout, returncode = "", 1

    monkeypatch.setattr(audit_verify.subprocess, "run", lambda *a, **k: Result())
    assert audit_verify.main(["--verify-key", "k", "--anchors", "/nonexistent", "--db", store.db_path]) == 2
    assert json.loads(capsys.readouterr().out)["problem"] == "journal_seal_failed"


# --- the witnesses ---------------------------------------------------------------------------


def test_heartbeat_carries_the_anchor_to_fleet(store, tmp_path, monkeypatch):
    from app.rights import agent

    path = tmp_path / "audit" / "anchor.json"
    monkeypatch.setattr(audit_anchor, "ANCHOR_FILE", path)
    assert agent.audit_anchor_for_fleet() is None
    anchor = audit_anchor.emit(store, out=io.StringIO(), path=path)
    assert agent.audit_anchor_for_fleet() == anchor.to_json()


def test_published_anchor_schema_matches(store):
    import jsonschema

    from tests.test_fleet_rights_api import schema

    jsonschema.validate(audit_anchor.current(store).to_json(), schema("AuditAnchor"))


def test_capabilities_show_the_witness(tmp_path, monkeypatch):
    from app.gate.ipc import _audit_status
    from app.rights import fleet_api

    class G:
        store = GateStore(str(tmp_path / "g.db"))

    monkeypatch.setattr(fleet_api, "ENROLLMENT_PATH", tmp_path / "none.json")
    from app.gate import audit_seal

    monkeypatch.setattr(audit_seal, "SEAL_DIR", tmp_path / "seal")
    assert _audit_status(G()) == {"seq": 0, "head": GENESIS, "witness": "journal_only",
                                  "seal": "journal_unsealed"}


def test_every_entry_is_anchored(store, monkeypatch):
    lines = io.StringIO()
    monkeypatch.setattr(audit_anchor, "emit", lambda s, **k: lines.write(f"{s.audit_head()[0]}\n"))
    anchorer = audit_anchor.Anchorer(store, interval=3600)
    anchorer.start()
    store.append_audit({"step": "a"})
    store.append_audit({"step": "b"})
    anchorer.stop()
    assert lines.getvalue().split() == ["5", "6", "7", "7"]  # start, two entries, stop
    store.append_audit({"step": "after stop"})
    assert lines.getvalue().split() == ["5", "6", "7", "7"]


def test_a_failing_anchor_never_fails_a_decision(store):
    store.audit_listeners.append(lambda: 1 / 0)
    store.append_audit({"step": "still recorded"})
    assert store.audit_head()[0] == 6


def test_a_failing_anchor_is_logged_and_never_fails_the_decision(tmp_path, caplog):
    """Fundregister S-13: the listener's error used to be swallowed without a
    trace. The entry is still written; the failure is logged as a warning."""
    import logging

    store = GateStore(str(tmp_path / "gate.db"))

    def fleet_anchor() -> None:
        raise ConnectionError("fleet unreachable")

    store.audit_listeners.append(fleet_anchor)
    with caplog.at_level(logging.WARNING, logger="eira.gate.audit"):
        entry_hash = store.append_audit({"event": "test"})
    assert store.audit_entries()[-1]["entry_hash"] == entry_hash
    assert store.verify_audit_chain()
    [record] = [r for r in caplog.records if r.name == "eira.gate.audit"]
    assert record.levelno == logging.WARNING
    assert "fleet_anchor" in record.getMessage()
    assert "ConnectionError: fleet unreachable" in record.getMessage()
    assert entry_hash in record.getMessage()
