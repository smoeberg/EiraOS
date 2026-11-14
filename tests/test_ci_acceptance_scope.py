"""What the packaging acceptance proves (UDVIKLINGSPLAN F0c.1, review G-19, G-20).

The workflow runs for every change that can alter the installed system, and
one final job is green only when the tests on Ubuntu 26.04 and the
installed-system acceptance in the VM both passed.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.safe_load((ROOT / ".github" / "workflows" / "packaging-acceptance.yml").read_text(encoding="utf-8"))
# PyYAML reads the key "on" as True.
TRIGGER = WORKFLOW[True]["pull_request"]


def _ignored(path: str) -> bool:
    # GitHub's "**/" also matches zero directories (README.md at the root).
    patterns = TRIGGER.get("paths-ignore", [])
    patterns = patterns + [p[3:] for p in patterns if p.startswith("**/")]
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def test_security_core_changes_run_the_acceptance():
    assert "paths" not in TRIGGER, "a list of included paths is how app/** was missed"
    for path in (
        "app/gate/kernel.py",
        "app/ipc/access.py",
        "app/auth/consent_agent.py",
        "crates/eira-consent-agent/src/agent.rs",
        "packaging/apparmor/usr.bin.eira-intentd",
        "systemd/eira-intentd.service",
        "requirements.txt",
        "Cargo.toml",
        "tests/test_gate_kernel.py",
        "scripts/build_deb.sh",
    ):
        assert not _ignored(path), path


def test_only_documentation_is_skipped():
    for path in ("docs/UDVIKLINGSPLAN.md", "specs/GATE-KERNEL-1.0.md", "README.md"):
        assert _ignored(path), path


def test_one_final_job_needs_every_other_job():
    jobs = WORKFLOW["jobs"]
    final = jobs["acceptance"]
    assert final["if"] == "always()"
    assert set(final["needs"]) == set(jobs) - {"acceptance"}
    assert {"tests-on-ubuntu-26-04", "vm-install-acceptance"} <= set(final["needs"])
    script = final["steps"][0]["run"]
    assert 'all(x == "success"' in script


def test_the_tests_on_26_04_run_python_rust_and_ui():
    runs = " ".join(step.get("run", "") for step in WORKFLOW["jobs"]["tests-on-ubuntu-26-04"]["steps"])
    assert "pytest" in runs and "cargo test --workspace" in runs and "npm test" in runs
    assert "alembic" not in runs
