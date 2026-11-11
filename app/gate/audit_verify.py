"""eira-audit-verify — check the gate's audit chain against its anchors.

    eira-audit-verify [--journal] [--anchors FILE] [--verify-key KEY]

--journal         anchors from intentd's journal (EIRA_AUDIT_ANCHOR lines)
--anchors FILE    anchors exported from Fleet: JSON list of {"seq", "head"}
--verify-key KEY  also check the journal's Forward Secure Sealing (the key
                  is kept off the machine; see GATE-KERNEL bilag A pkt. 2)

Exit: 0 chain valid and agrees with every anchor; 1 tampering detected;
2 nothing to verify against or the journal seal could not be checked.
Run as root (reads /data and the system journal).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from app.gate import audit_anchor

JOURNAL_UNIT = "eira-intentd.service"


def journal_anchors() -> list[audit_anchor.Anchor]:
    result = subprocess.run(
        ["journalctl", "-u", JOURNAL_UNIT, "-o", "cat", "--no-pager"],
        capture_output=True, text=True, check=False,
    )
    return audit_anchor.parse_journal(result.stdout.splitlines())


def file_anchors(path: Path) -> list[audit_anchor.Anchor]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [audit_anchor.Anchor(int(item["seq"]), str(item["head"]), item.get("at")) for item in data]


def journal_seal_ok(key: str) -> bool:
    # The system journal: that is where intentd writes its anchors. User
    # journals hold none, and journald's FSS tags in them fail verification
    # on Ubuntu 26.04 (seen in VM, see GATE-KERNEL bilag A pkt. 2).
    result = subprocess.run(["journalctl", "--system", "--verify", f"--verify-key={key}"],
                            capture_output=True, text=True, check=False)
    return result.returncode == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eira-audit-verify")
    parser.add_argument("--journal", action="store_true")
    parser.add_argument("--anchors", type=Path)
    parser.add_argument("--verify-key")
    parser.add_argument("--db")
    args = parser.parse_args(argv)

    from app.gate.store import GateStore

    # The seal first: anchors from a journal whose seal fails prove nothing.
    if args.verify_key and not journal_seal_ok(args.verify_key):
        print(json.dumps({"ok": False, "problem": "journal_seal_failed"}))
        return 2
    anchors: list[audit_anchor.Anchor] = []
    if args.journal:
        anchors += journal_anchors()
    if args.anchors:
        anchors += file_anchors(args.anchors)
    store = GateStore(args.db)
    if not anchors:
        verdict = audit_anchor.verify(store, [])
        print(json.dumps({"ok": verdict.ok, "anchors": 0, "problem": verdict.problem or "no_anchors"}))
        return 1 if not verdict.ok else 2
    verdict = audit_anchor.verify(store, anchors)
    print(json.dumps({"ok": verdict.ok, "anchors": verdict.checked, "problem": verdict.problem}))
    return 0 if verdict.ok else 1


if __name__ == "__main__":
    sys.exit(main())
