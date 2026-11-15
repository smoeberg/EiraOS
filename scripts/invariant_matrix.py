#!/usr/bin/env python3
"""The matrix of EiraOS' security invariants, generated from
docs/security/invarianter.toml.

    scripts/invariant_matrix.py --write   # docs/reference/sikkerhedsinvarianter.md
    scripts/invariant_matrix.py --check   # fail if the document is stale

For every invariant the matrix shows the tests (development default and
production mode), the mutants that must be caught and the VM checks on the
installed ISO (UDVIKLINGSPLAN F0c.3, vurderingen G-22).
tests/test_security_invariants.py checks that every reference exists.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "docs" / "security" / "invarianter.toml"
DOCUMENT = ROOT / "docs" / "reference" / "sikkerhedsinvarianter.md"


def load() -> list[dict]:
    with REGISTER.open("rb") as handle:
        return tomllib.load(handle)["invariant"]


def _names(refs: list[str]) -> str:
    if not refs:
        return "–"
    return "<br>".join(f"`{ref.split('::')[-1]}`" for ref in refs)


def _code(items: list[str]) -> str:
    return "<br>".join(f"`{item}`" for item in items) if items else "–"


def render(invariants: list[dict]) -> str:
    lines = [
        "# Sikkerhedsinvarianter",
        "",
        "Genereret af `scripts/invariant_matrix.py` fra "
        "[`docs/security/invarianter.toml`](../security/invarianter.toml). Ret i registret, ikke her.",
        "",
        "Hver række er en påstand fra [SIKKERHEDSMODEL](../security/SIKKERHEDSMODEL.md) og det, der beviser den. "
        "*Udvikling* er tests med udviklingsstandarden (`EIRA_ENV=development`, sockets uden for `/run/eira`). "
        "*Produktion* er tests, der selv sætter et installeret systems tilstand, bruger en rigtig kerne-peer "
        "eller læser de installerede filer. *VM* er checks på den installerede ISO "
        "(`packaging/installer/ci/eira-ci-report`). En mutant skal fanges af testene (`scripts/check-mutants.sh`).",
        "",
    ]
    no_production = [inv["id"] for inv in invariants
                     if not inv.get("production_tests") and not inv.get("vm")]
    with_gap = [inv["id"] for inv in invariants if inv.get("gap")]
    lines += [
        f"{len(invariants)} invarianter. Uden bevis i produktionstilstand (hverken test eller VM): "
        f"{', '.join(no_production) if no_production else 'ingen'}. Med et kendt hul: "
        f"{', '.join(with_gap) if with_gap else 'ingen'}.",
        "",
        "| ID | Påstand | Udvikling | Produktion | Mutanter | VM | Hul |",
        "|---|---|---|---|---|---|---|",
    ]
    for inv in invariants:
        lines.append(
            f"| {inv['id']} | {inv['claim']} ({inv['section']}) | {_names(inv.get('tests', []))} "
            f"| {_names(inv.get('production_tests', []))} | {_code(inv.get('mutants', []))} "
            f"| {_code(inv.get('vm', []))} | {inv.get('gap', '–')} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    text = render(load())
    if args.write:
        DOCUMENT.write_text(text, encoding="utf-8")
        return 0
    if not DOCUMENT.exists() or DOCUMENT.read_text(encoding="utf-8") != text:
        print(f"{DOCUMENT.relative_to(ROOT)} is stale: run scripts/invariant_matrix.py --write",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
