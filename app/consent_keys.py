"""Consent keys live in RAM only (EIRA-CONSENT-AGENT §5.3, EIRA-CONTEXT A-1).

A consent key lets its holder consent on the user's behalf. Kept in the
session database under /data, it survived a reboot and was on every copy of
the disk. Here it is kept apart from the session, in a small SQLite file on a
tmpfs (``/run/eira``) shared by the daemons that need it (identityd writes it,
the gate and delegationd read it), and every key is tied to the boot it was
made in:

* Nothing is written to persistent storage. The store refuses a path that is
  not on tmpfs, unless ``EIRA_CONSENT_KEYS_ALLOW_DISK=1`` (development and
  tests only; the installed units never set it).
* A key made in another boot is never returned, even if the file survived.
* Logging out deletes the key.

The target architecture keeps the key only in identityd and the consent
agent's memory (§5.3); this module is the step that gets it off the disk now.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from app.clock import boot_now

ALLOW_DISK_ENV = "EIRA_CONSENT_KEYS_ALLOW_DISK"
PATH_ENV = "EIRA_CONSENT_KEY_DB"
FILENAME = "consent-keys.db"


class ConsentKeyStoreError(RuntimeError):
    """The store would not be in RAM; refuse rather than write the key to disk."""


def _default_path() -> Path:
    run = Path("/run/eira")
    if run.is_dir() and os.access(run, os.W_OK):
        return run / FILENAME
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return Path(runtime) / f"eira-{FILENAME}"
    return run / FILENAME


def store_path() -> Path:
    configured = os.environ.get(PATH_ENV)
    return Path(configured) if configured else _default_path()


def _mount_type(path: Path) -> str | None:
    """Filesystem type of the mount holding ``path`` (longest mount prefix)."""
    target = str(path.resolve())
    best, kind = "", None
    try:
        with open("/proc/self/mounts", encoding="utf-8") as mounts:
            for line in mounts:
                fields = line.split()
                if len(fields) < 3:
                    continue
                point = fields[1].replace("\\040", " ")
                inside = target == point or target.startswith(point.rstrip("/") + "/")
                if inside and len(point) >= len(best):
                    best, kind = point, fields[2]
    except OSError:
        return None
    return kind


def _connect() -> sqlite3.Connection:
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.environ.get(ALLOW_DISK_ENV) != "1" and _mount_type(path.parent) not in {
        "tmpfs",
        "ramfs",
    }:
        raise ConsentKeyStoreError(f"consent keys must be on tmpfs, not {path}")
    # Created owner-only before SQLite opens it; never widened afterwards.
    os.close(os.open(path, os.O_RDWR | os.O_CREAT, 0o600))
    conn = sqlite3.connect(path)
    # No WAL or journal files beside the store, and freed pages are zeroed.
    conn.execute("PRAGMA journal_mode=MEMORY")
    conn.execute("PRAGMA secure_delete=ON")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS consent_keys ("
        " session_id TEXT PRIMARY KEY, boot_id TEXT NOT NULL, key TEXT NOT NULL)"
    )
    return conn


def put(session_id: str, key: str) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO consent_keys (session_id, boot_id, key) VALUES (?, ?, ?)",
            (session_id, boot_now().boot_id, key),
        )
        conn.commit()
    finally:
        conn.close()


def get(session_id: str) -> str | None:
    """The key for this session, if it was made in this boot. Fails closed."""
    try:
        conn = _connect()
    except (ConsentKeyStoreError, OSError, sqlite3.Error):
        return None
    try:
        row = conn.execute(
            "SELECT boot_id, key FROM consent_keys WHERE session_id = ?", (session_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None or row[0] != boot_now().boot_id:
        return None
    return row[1]


def forget(session_id: str) -> None:
    conn = _connect()
    try:
        conn.execute("DELETE FROM consent_keys WHERE session_id = ?", (session_id,))
        conn.commit()
    finally:
        conn.close()
