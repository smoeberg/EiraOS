"""The journal's Forward Secure Sealing (GATE-KERNEL bilag A pkt. 2): set up
once; the verification key leaves the device once, to Fleet or the owner."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from app.gate import audit_seal

REPO = Path(__file__).resolve().parents[1]
KEY = "a1b2c3-d4e5f6-0718293a/1c9a2b-35a4e900"


class Ran:
    def __init__(self, stdout=KEY + "\n", returncode=0):
        self.calls = []
        self.stdout, self.returncode = stdout, returncode

    def __call__(self, argv, **_):
        self.calls.append(argv)
        return type("R", (), {"returncode": self.returncode, "stdout": self.stdout, "stderr": "boom"})()


@pytest.fixture(autouse=True)
def seal_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(audit_seal, "SEAL_DIR", tmp_path / "seal")
    return tmp_path / "seal"


def test_setup_keeps_the_key_until_handover_and_starts_sealing(seal_dir):
    run = Ran()
    assert audit_seal.status() == "journal_unsealed"
    assert audit_seal.setup(run) == 0
    assert run.calls == [["journalctl", "--setup-keys", "--interval=15min"], ["journalctl", "--rotate"]]
    assert audit_seal.status() == "sealed_key_on_device" and audit_seal.pending_key() == KEY
    assert stat.S_IMODE((seal_dir / "verify-key").stat().st_mode) == 0o640


def test_setup_runs_once(seal_dir):
    audit_seal.setup(Ran())
    again = Ran()
    assert audit_seal.setup(again) == 0 and again.calls == []


@pytest.mark.parametrize("ran", [Ran(stdout="no key here\n"), Ran(returncode=1)])
def test_a_failed_setup_records_nothing(ran):
    assert audit_seal.setup(ran) == 1
    assert audit_seal.status() == "journal_unsealed"


def test_the_key_is_found_in_journalctl_s_output():
    assert audit_seal.parse_key(f"Bla bla\n\n{KEY}\n") == KEY
    assert audit_seal.parse_key("aabb\n") is None


def test_the_owner_sees_it_once_and_it_is_deleted(seal_dir, capsys):
    audit_seal.setup(Ran())
    assert audit_seal.main(["show"]) == 0
    assert KEY in capsys.readouterr().out
    assert not (seal_dir / "verify-key").exists()
    assert audit_seal.status() == "sealed" and audit_seal.state()["state"] == "owner"
    assert audit_seal.main(["show"]) == 1  # gone
    assert audit_seal.for_fleet() is None


def test_fleet_gets_it_with_the_machine_and_interval(seal_dir):
    audit_seal.setup(Ran())
    sent = audit_seal.for_fleet()
    assert sent["verify_key"] == KEY and sent["interval"] == "15min" and "machine_id" in sent
    audit_seal.handed_over("fleet")
    assert audit_seal.for_fleet() is None and not (seal_dir / "verify-key").exists()


def test_a_tampered_key_file_is_not_sent(seal_dir):
    audit_seal.setup(Ran())
    (seal_dir / "verify-key").write_text("anything\n")
    assert audit_seal.for_fleet() is None


def test_packaging_sets_it_up_once_at_boot():
    unit = (REPO / "packaging/audit/eira-audit-seal.service").read_text()
    assert "ExecStart=/usr/bin/eira-audit-seal setup" in unit
    assert "ConditionPathExists=!/var/lib/eira-audit-seal/state.json" in unit
    assert "ConditionPathIsDirectory=/var/log/journal" in unit
    postinst = (REPO / "packaging/debian/postinst").read_text()
    assert "install -d -o root -g eira -m 2770 /var/lib/eira-audit-seal" in postinst
    assert "systemctl enable eira-audit-seal.service" in postinst
    # The gate reads only the state, never the key.
    intentd = (REPO / "packaging/apparmor/usr.bin.eira-intentd").read_text()
    assert "/var/lib/eira-audit-seal/state.json r," in intentd and "verify-key" not in intentd


def test_what_fleet_gets_matches_the_published_schema():
    import jsonschema

    from tests.test_fleet_rights_api import schema

    audit_seal.setup(Ran())
    jsonschema.validate(audit_seal.for_fleet(), schema("AuditSeal"))
