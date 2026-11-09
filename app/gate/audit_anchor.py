"""External anchors for the gate's audit chain (GATE-KERNEL bilag A pkt. 2).

The chain in gate_audit is hash-linked and append-only, so it exposes edits
by anyone but the writer. It cannot show that the writer (or root) rewrote
the whole chain. Anchors fix (seq, head) pairs outside the database:

- **journald** — intentd logs `EIRA_AUDIT_ANCHOR {...}` to its journal at
  start, every ANCHOR_INTERVAL and at stop. With Forward Secure Sealing the
  journal cannot be rewritten later without the seal failing; the
  verification key lives off the machine.
- **Fleet** — the same anchor goes into the rights agent's heartbeat
  (FLEET-RIGHTS-API §3.3). Fleet keeps every (seq, head) it has seen; a
  rewritten chain no longer reproduces them.

What it does not cover, said plainly: a compromised intentd can anchor a
false head; the journal is only sealed every sealing interval (entries since
the last seal can be rewritten together with their anchor lines); a
standalone machine without Fleet has only the journal.

`verify` checks a chain against any set of anchors (from the journal, from
Fleet, or both): each anchored position must still carry the anchored head,
and the chain must not be shorter than an anchor says it was.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, TextIO

PREFIX = "EIRA_AUDIT_ANCHOR "
ANCHOR_INTERVAL_SECONDS = 300
ANCHOR_FILE = Path(os.environ.get("EIRA_AUDIT_ANCHOR_FILE", "/data/audit/anchor.json"))


@dataclass(frozen=True)
class Anchor:
    seq: int
    head: str
    at: str | None = None

    def to_json(self) -> dict:
        return {"seq": self.seq, "head": self.head, "at": self.at}


def current(store) -> Anchor:
    seq, head = store.audit_head()
    return Anchor(seq, head, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))


def emit(store, *, out: TextIO | None = None, path: Path | None = None) -> Anchor:
    """Write the anchor to the journal (stdout of the unit) and the file the
    rights agent forwards to Fleet."""
    anchor = current(store)
    stream = out or sys.stdout
    stream.write(PREFIX + json.dumps(anchor.to_json(), sort_keys=True) + "\n")
    stream.flush()
    target = path or ANCHOR_FILE
    try:
        target.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
        os.chmod(target.parent, 0o750)  # UMask=0117 would leave it without x
        fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".anchor.")
        with os.fdopen(fd, "w") as handle:
            json.dump(anchor.to_json(), handle)
        os.chmod(tmp, 0o640)
        os.replace(tmp, target)
    except OSError:
        pass  # the journal anchor stands on its own
    return anchor


def parse_journal(lines: Iterable[str]) -> list[Anchor]:
    anchors = []
    for line in lines:
        index = line.find(PREFIX)
        if index < 0:
            continue
        try:
            data = json.loads(line[index + len(PREFIX):])
            anchors.append(Anchor(int(data["seq"]), str(data["head"]), data.get("at")))
        except (ValueError, KeyError, TypeError):
            continue  # a malformed line is not an anchor; never trusted either way
    return anchors


@dataclass(frozen=True)
class Verdict:
    ok: bool
    checked: int
    problem: str | None = None


def verify(store, anchors: Iterable[Anchor]) -> Verdict:
    """The chain must be internally valid and agree with every anchor."""
    if not store.verify_audit_chain():
        return Verdict(False, 0, "chain_broken")
    heads = store.audit_heads()  # seq -> entry_hash, plus 0 -> genesis
    last = max(heads)
    checked = 0
    for anchor in sorted(anchors, key=lambda a: a.seq):
        if anchor.seq > last:
            return Verdict(False, checked, f"chain_shorter_than_anchor:seq={anchor.seq}")
        if heads.get(anchor.seq) != anchor.head:
            return Verdict(False, checked, f"head_mismatch:seq={anchor.seq}")
        checked += 1
    return Verdict(True, checked)


class Anchorer:
    """intentd's anchoring: after every audit entry (no window in which the
    newest entries are unanchored), plus at start, every interval and at
    stop so a quiet gate still shows it is alive."""

    def __init__(self, store, interval: float = ANCHOR_INTERVAL_SECONDS):
        self._store = store
        self._interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="audit-anchor", daemon=True)

    def start(self) -> None:
        emit(self._store)
        self._store.audit_listeners.append(self._on_append)
        self._thread.start()

    def _on_append(self) -> None:
        emit(self._store)

    def stop(self) -> None:
        if self._on_append in self._store.audit_listeners:
            self._store.audit_listeners.remove(self._on_append)
        self._stop.set()
        self._thread.join(timeout=5)
        emit(self._store)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            emit(self._store)
