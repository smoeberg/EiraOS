"""The security invariants point at evidence that exists (UDVIKLINGSPLAN F0c.3,
vurderingen G-22).

docs/security/invarianter.toml names, for every invariant, the tests, mutants
and VM checks that prove it. A renamed test, a removed VM check or a mutant
that no invariant claims fails here, and the generated matrix must be current.
"""

from __future__ import annotations

import ast
import re
import sys
from functools import cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import invariant_matrix  # noqa: E402

INVARIANTS = invariant_matrix.load()
CI_REPORT = ROOT / "packaging" / "installer" / "ci" / "eira-ci-report"
MUTANTS = ROOT / "tests" / "mutants" / "make_mutants.py"
FIELDS = {"id", "section", "claim", "tests", "production_tests", "mutants", "vm", "gap"}


@cache
def _test_names(path: str) -> frozenset[str]:
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.add(f"{node.name}::{item.name}")
    return frozenset(names)


@cache
def _vm_checks() -> frozenset[str]:
    text = CI_REPORT.read_text(encoding="utf-8")
    names = set(re.findall(r"(?m)^\s*(?:check|daemon_write_as)\s+([a-z0-9][a-z0-9-]*)\b", text))
    names |= set(re.findall(r'say "([a-z0-9][a-z0-9-]*) (?:PASS|FAIL)', text))
    return frozenset(names)


@cache
def _mutants() -> frozenset[str]:
    return frozenset(re.findall(r'(?m)^    "([A-Z0-9]+-[A-Z0-9-]+)": \{', MUTANTS.read_text(encoding="utf-8")))


def _ids(inv: dict) -> str:
    return inv["id"]


def test_ids_are_unique_and_in_order():
    ids = [inv["id"] for inv in INVARIANTS]
    assert ids == [f"I-{n}" for n in range(1, len(ids) + 1)]


@pytest.mark.parametrize("inv", INVARIANTS, ids=_ids)
def test_every_invariant_has_a_claim_and_evidence(inv):
    assert set(inv) <= FIELDS, set(inv) - FIELDS
    assert inv["claim"].strip() and inv["section"].startswith("§")
    assert inv.get("tests") or inv.get("production_tests"), "an invariant needs at least one test"


@pytest.mark.parametrize("inv", INVARIANTS, ids=_ids)
def test_every_named_test_exists(inv):
    refs = inv.get("tests", []) + inv.get("production_tests", [])
    assert len(refs) == len(set(refs)), "a test is listed twice"
    for ref in refs:
        path, _, name = ref.partition("::")
        assert (ROOT / path).is_file(), ref
        assert name in _test_names(path), ref


@pytest.mark.parametrize("inv", INVARIANTS, ids=_ids)
def test_every_named_mutant_and_vm_check_exists(inv):
    assert set(inv.get("mutants", [])) <= _mutants(), set(inv.get("mutants", [])) - _mutants()
    assert set(inv.get("vm", [])) <= _vm_checks(), set(inv.get("vm", [])) - _vm_checks()


def test_every_gate_and_ipc_mutant_belongs_to_an_invariant():
    claimed = {m for inv in INVARIANTS for m in inv.get("mutants", [])}
    security = {m for m in _mutants() if m.startswith(("GATE-", "IPC-"))}
    assert security - claimed == set()


def test_an_invariant_without_production_evidence_says_so():
    for inv in INVARIANTS:
        if not inv.get("production_tests") and not inv.get("vm"):
            assert inv.get("gap"), f"{inv['id']} is only proven in development and must name the gap"


def test_the_vm_check_reader_finds_the_checks():
    # Guard against a reader that finds nothing and so accepts nothing.
    assert {"user-cannot-write-stated", "fleetd-may-append-state", "consent-agent-setgid"} <= _vm_checks()


def test_the_matrix_document_is_current():
    assert invariant_matrix.main(["--check"]) == 0
