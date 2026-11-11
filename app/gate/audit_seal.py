"""Forward Secure Sealing of the journal (GATE-KERNEL bilag A pkt. 2, drift).

journald seals the journal every interval with a key that evolves forward
and forgets the past, so root cannot later rewrite sealed entries without
detection. The *verification key* can regenerate every sealing key, so it
must not stay on the machine. Its life here:

1. ``setup`` (root, first boot, eira-audit-seal.service): ``journalctl
   --setup-keys`` creates the sealing key and prints the verification key,
   which is kept only until it is handed over (state ``pending_handover``).
2. Handover, once:
   - managed (enrolled): the next heartbeat carries it to Fleet
     (FLEET-RIGHTS-API §3.3 ``audit_seal``); on success it is deleted here
     (state ``fleet``);
   - private: the owner runs ``sudo eira-audit-seal show``, writes it down
     or stores it offline; it is shown once and deleted (state ``owner``).
3. ``eira-audit-verify --journal --verify-key KEY`` checks the seal wherever
   the key is.

Honest limit: until the handover, the key is on disk (root:eira 0640).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SEAL_DIR = Path(os.environ.get("EIRA_AUDIT_SEAL_DIR", "/var/lib/eira-audit-seal"))
INTERVAL = "15min"
# journalctl --setup-keys prints "<seed hex in groups>/<start>-<interval>".
KEY_RE = re.compile(r"^[0-9a-f]+(?:-[0-9a-f]+)*/[0-9a-f]+-[0-9a-f]+$")

STATES = ("pending_handover", "fleet", "owner")


def _key_file() -> Path:
    return SEAL_DIR / "verify-key"


def _state_file() -> Path:
    return SEAL_DIR / "state.json"


def state() -> dict[str, Any] | None:
    try:
        data = json.loads(_state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("state") in STATES else None


def _write_state(value: str, **extra: Any) -> None:
    current = state() or {}
    current.update({"state": value, "changed_at": datetime.now(timezone.utc).isoformat(), **extra})
    tmp = _state_file().with_suffix(".tmp")
    tmp.write_text(json.dumps(current, sort_keys=True), encoding="utf-8")
    os.chmod(tmp, 0o660)
    os.replace(tmp, _state_file())


def parse_key(output: str) -> str | None:
    for line in output.splitlines():
        line = line.strip()
        if KEY_RE.match(line):
            return line
    return None


def setup(run=subprocess.run) -> int:
    """Once per installation. Exit 0 also when already done."""
    if state() is not None:
        return 0
    # postinst creates it root:eira 2770 (setgid: the rights sync, running as
    # eira, may read and delete the key after handing it to Fleet).
    SEAL_DIR.mkdir(mode=0o2770, parents=True, exist_ok=True)
    result = run(["journalctl", "--setup-keys", f"--interval={INTERVAL}"],
                 capture_output=True, text=True, check=False)
    key = parse_key(result.stdout)
    if result.returncode != 0 or key is None:
        print(f"eira-audit-seal: setup failed: {result.stderr.strip() or 'no key printed'}", file=sys.stderr)
        return 1
    tmp = _key_file().with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)
    with os.fdopen(fd, "w", encoding="ascii") as out:
        out.write(key + "\n")
    os.chmod(tmp, 0o640)
    os.replace(tmp, _key_file())
    _write_state("pending_handover", interval=INTERVAL, created_at=datetime.now(timezone.utc).isoformat())
    # Start sealing now, not at the next rotation.
    run(["journalctl", "--rotate"], capture_output=True, check=False)
    return 0


def pending_key() -> str | None:
    if (state() or {}).get("state") != "pending_handover":
        return None
    try:
        key = _key_file().read_text(encoding="ascii").strip()
    except OSError:
        return None
    return key if KEY_RE.match(key) else None


def handed_over(to: str) -> None:
    """The key has left the machine: delete it, then record where it went."""
    try:
        _key_file().unlink()
    except FileNotFoundError:
        pass
    _write_state(to)


def for_fleet() -> dict[str, Any] | None:
    """The heartbeat field while a key waits for handover (§3.3)."""
    key = pending_key()
    if key is None:
        return None
    machine_id = Path("/etc/machine-id").read_text(encoding="ascii").strip() if Path("/etc/machine-id").exists() else ""
    return {"verify_key": key, "interval": (state() or {}).get("interval", INTERVAL), "machine_id": machine_id}


def status() -> str:
    """For gate status: ``journal_unsealed`` (no FSS), ``sealed_key_on_device``
    (sealing, key not yet handed over) or ``sealed``."""
    current = (state() or {}).get("state")
    if current is None:
        return "journal_unsealed"
    return "sealed_key_on_device" if current == "pending_handover" else "sealed"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args == ["setup"]:
        return setup()
    if args == ["status"]:
        print(status())
        return 0
    if args == ["show"]:
        key = pending_key()
        if key is None:
            print("Ingen nøgle venter: den er overdraget (" + str((state() or {}).get("state")) + ").",
                  file=sys.stderr)
            return 1
        print("Verifikationsnøgle til journalens segl. Gem den uden for maskinen (papir eller")
        print("offline-medie). Den vises kun denne ene gang og slettes nu fra maskinen.")
        print()
        print(key)
        print()
        print("Kontrol: sudo eira-audit-verify --journal --verify-key '<nøglen>'")
        handed_over("owner")
        return 0
    print("usage: eira-audit-seal setup | status | show", file=sys.stderr)
    return 64


if __name__ == "__main__":
    raise SystemExit(main())
