"""The endpoint's copy of the active rights set (EIRA-RIGHTS-SET-1.0 §4–§6).

One component, two callers: `eira-governance-agent` installs a set that
`contract.verify` accepted; the gate reads it at every decision. The cache
is never a source of rights — it only holds what Fleet signed.

It also keeps the effective time (§4.1), because the time that decides
whether the set is still valid must survive a wall clock set back:

    effective_now = max(wall_now, high_water, issued_at + elapsed_since_apply)

`elapsed_since_apply` is CLOCK_BOOTTIME accumulated across boots. Files are
written atomically (rename) under a lock; only the service user can write the
directory (0700 eira, created by the package).
"""

from __future__ import annotations

import fcntl
import json
import os
import stat
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from app.clock import BootInstant, boot_now
from app.rights import contract

ROLLBACK_TOLERANCE = timedelta(minutes=5)
SET_FILE = "active.json"
STATE_FILE = "state.json"


@dataclass(frozen=True)
class ActiveRights:
    rights_set: dict[str, Any]
    rights_set_id: str
    version: int
    kind: str
    expires_at: datetime
    effective_now: datetime
    clock_rollback: bool

    @property
    def expired(self) -> bool:
        return self.effective_now >= self.expires_at

    @property
    def owner_admin(self) -> bool:
        """ADR-0003: an unmanaged machine runs the bundle's default set, and
        its single account has sudo. The gate never claims more than that."""
        return self.kind == "default"

    def audit(self) -> dict[str, Any]:
        return {
            "rights_set_id": self.rights_set_id,
            "rights_version": self.version,
            "rights_kind": self.kind,
            "rights_template": self.rights_set["template"]["id"],
            "rights_api_call_id": self.rights_set["issued_by"]["api_call_id"],
            "owner_admin": self.owner_admin,
            "clock_rollback": self.clock_rollback,
        }


def default_directory() -> Path:
    explicit = os.environ.get("EIRA_RIGHTS_DIR")
    if explicit:
        return Path(explicit)
    from app.session_store import get_db_path

    return Path(get_db_path()).resolve().parent / "rights"


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


class RightsCache:
    def __init__(
        self,
        directory: str | os.PathLike[str] | None = None,
        *,
        boot_clock=boot_now,
    ) -> None:
        self.directory = Path(directory) if directory is not None else default_directory()
        self._boot_clock = boot_clock

    # --- agent side ----------------------------------------------------------

    def install(self, raw: bytes, verdict: contract.Verdict, wall_now: datetime) -> None:
        """Replace the active set atomically. Only a verdict from
        `contract.verify` on exactly these bytes may be installed."""
        if not verdict.ok or verdict.rights_set is None:
            raise ValueError("refusing to install a rejected rights set")
        if verdict.noop:
            return
        doc = verdict.rights_set
        if contract.content_hash(contract.parse(raw)) != verdict.content_hash:
            raise ValueError("verdict does not belong to these bytes")
        boot = self._boot_clock()
        with self._locked():
            state = self._read_state() or {}
            state.update(
                {
                    "content_hash": verdict.content_hash,
                    "rights_set_id": doc["rights_set_id"],
                    "version": doc["version"],
                    "kind": doc["kind"],
                    "tenant_id": doc["tenant_id"],
                    "issued_at": doc["issued_at"],
                    "expires_at": doc["expires_at"],
                    "elapsed_ns": 0,
                    "last": {"boot_id": boot.boot_id, "ns": boot.ns},
                    "high_water": _iso(max(wall_now, _parse(state["high_water"])))
                    if "high_water" in state
                    else _iso(wall_now),
                }
            )
            # Set first, then state: a crash in between leaves the old state,
            # whose content_hash no longer matches → `current` fails closed.
            self._write(SET_FILE, bytes(raw))
            self._write(STATE_FILE, json.dumps(state, sort_keys=True).encode())

    def active_meta(self) -> contract.Active | None:
        """What `contract.verify` needs to judge the next set (§4 rule 6)."""
        state = self._read_state()
        if not state:
            return None
        return contract.Active(state["version"], state["content_hash"], state["tenant_id"])

    def high_water(self) -> datetime | None:
        state = self._read_state()
        return _parse(state["high_water"]) if state and "high_water" in state else None

    # --- gate side -----------------------------------------------------------

    def current(self, wall_now: datetime) -> ActiveRights | None:
        """The active set and the effective time, advanced and persisted.
        Missing, inconsistent or unreadable → None (no rights, fail closed)."""
        boot = self._boot_clock()
        try:
            with self._locked():
                state = self._read_state()
                raw = self._read(SET_FILE)
                if not state or raw is None:
                    return None
                doc = contract.parse(raw)
                if contract.content_hash(doc) != state["content_hash"]:
                    return None
                elapsed = int(state["elapsed_ns"]) + _since(state["last"], boot)
                high_water = _parse(state["high_water"])
                rollback = wall_now < high_water - ROLLBACK_TOLERANCE
                effective = max(
                    wall_now,
                    high_water,
                    _parse(state["issued_at"]) + timedelta(microseconds=elapsed // 1000),
                )
                state["elapsed_ns"] = elapsed
                state["last"] = {"boot_id": boot.boot_id, "ns": boot.ns}
                state["high_water"] = _iso(effective)
                self._write(STATE_FILE, json.dumps(state, sort_keys=True).encode())
        except (OSError, ValueError, KeyError, contract._Reject):
            return None
        return ActiveRights(
            rights_set=doc,
            rights_set_id=doc["rights_set_id"],
            version=doc["version"],
            kind=doc["kind"],
            expires_at=_parse(doc["expires_at"]),
            effective_now=effective,
            clock_rollback=rollback,
        )

    # --- files ---------------------------------------------------------------

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        # The daemons run with UMask=0117, which also strips the owner's x bit:
        # mkdir(0o700) yields 0600, a directory not even its owner can enter.
        # chmod is not subject to the umask (found in the VM).
        if stat.S_IMODE(self.directory.stat().st_mode) != 0o700:
            os.chmod(self.directory, 0o700)
        with open(self.directory / ".lock", "a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _read(self, name: str) -> bytes | None:
        try:
            return (self.directory / name).read_bytes()
        except FileNotFoundError:
            return None

    def _read_state(self) -> dict[str, Any] | None:
        raw = self._read(STATE_FILE)
        return json.loads(raw) if raw else None

    def _write(self, name: str, data: bytes) -> None:
        fd, tmp = tempfile.mkstemp(dir=self.directory, prefix=f".{name}.")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.directory / name)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


def _since(last: dict[str, Any], now: BootInstant) -> int:
    """CLOCK_BOOTTIME elapsed since the last persisted instant. In a new boot
    the clock restarted at 0, so the time since this boot began is what is
    known; time between the last write and power-off is not counted."""
    if last.get("boot_id") == now.boot_id:
        return max(0, now.ns - int(last["ns"]))
    return max(0, now.ns)
