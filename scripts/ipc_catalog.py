#!/usr/bin/env python3
"""The JSON-RPC catalogue, generated from the daemons' own registrations.

Every production daemon (packaging/daemon-policy.json) and the model process
is registered against a recording server in a throw-away data directory; the
access class of each method (app/ipc/access.py) is read from its handler.

    scripts/ipc_catalog.py --json            # machine-readable, for tests
    scripts/ipc_catalog.py --write           # docs/reference/ipc-katalog.md
    scripts/ipc_catalog.py --check           # fail if the document is stale

The catalogue is generated so it cannot drift from the code
(UDVIKLINGSPLAN F0b.2, fundregister D-5).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "reference" / "ipc-katalog.md"
POLICY = ROOT / "packaging" / "daemon-policy.json"

PROBE = r"""
import json, sys
from app.ipc.access import access_of
from app.daemons.runner import REGISTRARS

class Recorder:
    def __init__(self):
        self.methods = {}
    def register(self, name, handler):
        kind = access_of(handler)
        self.methods[name] = {
            "access": kind.value if kind else None,
            "note": getattr(handler, "access_note", None),
            "wants_peer": bool(getattr(handler, "wants_peer", False)),
        }
    def add_cleanup(self, callback):
        pass

daemon = sys.argv[1]
server = Recorder()
if daemon == "modeld":
    from app.model.daemon import register_model_handlers
    register_model_handlers(server)
else:
    REGISTRARS[daemon](server)
print(json.dumps(server.methods))
"""


def production_daemons() -> list[str]:
    return list(json.loads(POLICY.read_text())["production_daemons"]) + ["modeld"]


def collect() -> dict[str, dict[str, dict]]:
    """{daemon: {method: {access, note, wants_peer}}}; each daemon registers in
    its own process and data directory, because registration has side effects."""
    catalogue: dict[str, dict[str, dict]] = {}
    for daemon in production_daemons():
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                **{k: v for k, v in os.environ.items() if not k.startswith("EIRA_")},
                "PYTHONPATH": str(ROOT),
                "HOME": tmp,
                "EIRA_DB_PATH": f"{tmp}/app.db",
                "EIRA_APP_DB": f"{tmp}/app.db",
                "EIRA_STATE_DB": f"{tmp}/state.db",
                "EIRA_STATE_BACKEND": "python",
                "EIRA_RUN_DIR": f"{tmp}/run",
                "EIRA_RIGHTS_DIR": f"{tmp}/rights",
                "EIRA_DATA_DIR": f"{tmp}/data",
            }
            result = subprocess.run(
                [sys.executable, "-c", PROBE, daemon],
                cwd=tmp, env=env, capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                raise RuntimeError(f"{daemon} did not register: {result.stderr[-2000:]}")
            catalogue[daemon] = json.loads(result.stdout.strip().splitlines()[-1])
    return catalogue


MEANING = {
    "read": "Læser kun. Enhver klient på socketen.",
    "daemon_write": "Ændrer tilstand. Kun EiraOS' egne tjenester (samme UID); serveren tjekker det.",
    "caller": "Handleren afgør ud fra kalderen fra kernen (`SO_PEERCRED`).",
    "signed": "Handleren tjekker et kryptografisk bevis i forespørgslen.",
    "refused": "Afviser altid; gammel vej, der skal gennem gaten.",
    "open_write": "**Kendt hul:** ændrer tilstand uden tjek. Lukkes af det nævnte plan-id.",
}


def render(catalogue: dict[str, dict[str, dict]]) -> str:
    sys.path.insert(0, str(ROOT))
    from app.ipc.paths import DAEMON_SOCKETS, MODEL_RUN_DIR

    lines = [
        "# IPC-katalog",
        "",
        "**Genereret** af `scripts/ipc_catalog.py --write` fra daemons' egne registreringer."
        " Ret ikke i hånden; CI fejler, hvis dokumentet ikke svarer til koden.",
        "",
        "Hver metode har en adgangsklasse ([`app/ipc/access.py`](../../app/ipc/access.py))."
        " Socket-gruppen `eira-clients` og IPC-tokenet er ikke en grænse mod desktop-brugeren;"
        " klasserne er.",
        "",
        "| Klasse | Betydning |",
        "|---|---|",
    ]
    lines += [f"| `{kind}` | {text} |" for kind, text in MEANING.items()]
    for daemon, methods in catalogue.items():
        socket = (MODEL_RUN_DIR if daemon == "modeld" else Path("/run/eira")) / DAEMON_SOCKETS[daemon]
        lines += ["", f"## `{daemon}` — `{socket}`", "", "| Metode | Klasse | Bemærkning |", "|---|---|---|"]
        for method in sorted(methods):
            info = methods[method]
            note = f"Lukkes af {info['note']}" if info["note"] else ""
            lines.append(f"| `{method}` | `{info['access']}` | {note} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--json", action="store_true")
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    catalogue = collect()
    if args.json:
        print(json.dumps(catalogue, indent=2, sort_keys=True))
        return 0
    text = render(catalogue)
    if args.write:
        DOC.parent.mkdir(parents=True, exist_ok=True)
        DOC.write_text(text, encoding="utf-8")
        return 0
    if not DOC.exists() or DOC.read_text(encoding="utf-8") != text:
        print(f"{DOC.relative_to(ROOT)} is stale: run scripts/ipc_catalog.py --write", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
