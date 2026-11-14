"""The security mutants are generated from one source and run in CI
(UDVIKLINGSPLAN F0c.2, review G-21)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MUTANTS_DIR = ROOT / "tests" / "mutants"


def _generator():
    spec = importlib.util.spec_from_file_location("make_mutants", MUTANTS_DIR / "make_mutants.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_mutant_has_its_patch_and_no_patch_is_orphaned():
    names = set(_generator().MUTANTS)
    patches = {p.stem for p in MUTANTS_DIR.glob("*.patch")}
    assert names == patches
    assert any(n.startswith("GATE-") for n in names) and any(n.startswith("IPC-") for n in names)


def test_ci_runs_the_context_and_the_security_mutants():
    jobs = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))["jobs"]
    runs = {name: " ".join(step.get("run", "") for step in job["steps"]) for name, job in jobs.items()}
    assert "check-mutants.sh 'GATE-*' 'IPC-*'" in runs["security-mutants"]
    assert "check-mutants.sh 'CTX-*'" in runs["context-home"]


def test_only_a_failing_test_counts_as_caught():
    script = (ROOT / "scripts" / "check-mutants.sh").read_text(encoding="utf-8")
    assert "BROKE THE RUN" in script
    assert "        1)\n            echo \"MUTANT $name: caught\"" in script
