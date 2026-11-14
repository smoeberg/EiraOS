"""The consent key never reaches persistent storage (EIRA-CONSENT-AGENT §5.3,
EIRA-CONTEXT A-1): a copy of the disk must not hold a usable consent key,
and no key survives a reboot."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app import consent_keys, session_store
from app.clock import BootInstant

CLAIMS = {"sub": "u1", "identity": "did:eira:test.u1", "groups": []}


@pytest.fixture
def app_db(tmp_path, monkeypatch):
    path = tmp_path / "eira-app.db"
    monkeypatch.setenv("EIRA_DB_PATH", str(path))
    monkeypatch.delenv("EIRA_APP_DB", raising=False)
    return path


def test_login_writes_no_consent_key_to_the_session_database(app_db):
    sid = session_store.create_session_from_claims(CLAIMS, os_uid=1000)
    key = session_store.get_session_for_gate(sid)["consent_key"]
    assert key and len(key) == 64
    raw = app_db.read_bytes()
    assert key.encode() not in raw
    with sqlite3.connect(app_db) as conn:
        assert conn.execute("SELECT consent_key FROM sessions").fetchall() == [(None,)]


def test_key_from_another_boot_is_never_returned(app_db, monkeypatch):
    sid = session_store.create_session_from_claims(CLAIMS, os_uid=1000)
    assert session_store.get_session_for_gate(sid)["consent_key"]
    monkeypatch.setattr(consent_keys, "boot_now", lambda: BootInstant("another-boot", 0))
    assert session_store.get_session_for_gate(sid)["consent_key"] is None


def test_upgrade_erases_keys_earlier_versions_stored(app_db):
    session_store.init_db()
    old_key = "ab" * 32
    with sqlite3.connect(app_db) as conn:
        conn.execute(
            "INSERT INTO sessions (session_id, consent_key) VALUES ('old', ?)", (old_key,)
        )
        conn.commit()
    session_store.init_db()
    with sqlite3.connect(app_db) as conn:
        assert conn.execute("SELECT consent_key FROM sessions").fetchall() == [(None,)]
    assert old_key.encode() not in app_db.read_bytes()


def test_store_refuses_a_path_that_is_not_tmpfs(tmp_path, monkeypatch):
    monkeypatch.delenv(consent_keys.ALLOW_DISK_ENV)
    monkeypatch.setattr(consent_keys, "_mount_type", lambda path: "ext4")
    with pytest.raises(consent_keys.ConsentKeyStoreError):
        consent_keys.put("s1", "00" * 32)
    assert consent_keys.get("s1") is None


def test_login_fails_rather_than_store_the_key_on_disk(app_db, monkeypatch):
    monkeypatch.delenv(consent_keys.ALLOW_DISK_ENV)
    monkeypatch.setattr(consent_keys, "_mount_type", lambda path: "ext4")
    with pytest.raises(consent_keys.ConsentKeyStoreError):
        session_store.create_session_from_claims(CLAIMS, os_uid=1000)


def test_store_accepts_tmpfs(monkeypatch):
    monkeypatch.delenv(consent_keys.ALLOW_DISK_ENV)
    monkeypatch.setattr(consent_keys, "_mount_type", lambda path: "tmpfs")
    consent_keys.put("s2", "11" * 32)
    assert consent_keys.get("s2") == "11" * 32
    consent_keys.forget("s2")
    assert consent_keys.get("s2") is None


def test_store_file_is_owner_only():
    consent_keys.put("s3", "22" * 32)
    assert consent_keys.store_path().stat().st_mode & 0o777 == 0o600


def test_mount_type_finds_the_longest_mount_prefix():
    # /proc is always a proc mount on Linux.
    assert consent_keys._mount_type(Path("/proc/self")) == "proc"


def test_installed_units_keep_keys_on_run_and_never_allow_disk():
    root = Path(__file__).resolve().parent.parent
    for daemon in ("identityd", "intentd", "delegationd"):
        unit = (root / "systemd" / f"eira-{daemon}.service").read_text()
        assert "Environment=EIRA_CONSENT_KEY_DB=/run/eira/consent-keys.db" in unit
        assert consent_keys.ALLOW_DISK_ENV not in unit
        profile = (root / "packaging" / "apparmor" / f"usr.bin.eira-{daemon}").read_text()
        # Only identityd writes the keys; the gate and delegationd read them
        # (UDVIKLINGSPLAN F1c.2, review G-34).
        expected = "rwk" if daemon == "identityd" else "rk"
        assert f"/run/eira/consent-keys.db {expected}," in profile
        assert "/data/consent" not in profile
    for profile in (root / "packaging" / "apparmor").iterdir():
        if profile.name != "usr.bin.eira-identityd":
            text = profile.read_text()
            assert "consent-keys.db rw" not in text and "consent-keys.db w" not in text, profile.name
