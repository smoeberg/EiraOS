"""What the packaging acceptance proves (UDVIKLINGSPLAN F0c.1, review G-19, G-20).

The workflow runs for every change that can alter the installed system, and
one final job is green only when the tests on Ubuntu 26.04 and the
installed-system acceptance in the VM both passed.
"""

from __future__ import annotations

import fnmatch
import json
import os
import sys
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
    assert {"tests-on-ubuntu-26-04", "vm-install-acceptance", "vm-upgrade-acceptance"} <= set(final["needs"])


def _verdict(results: dict[str, str], event: str) -> int:
    import subprocess

    script = WORKFLOW["jobs"]["acceptance"]["steps"][0]["run"]
    code = script.split("python3 -c '", 1)[1].rsplit("'", 1)[0]
    needs = json.dumps({job: {"result": result} for job, result in results.items()})
    return subprocess.run([sys.executable, "-c", code], input=needs, text=True,
                          env={**os.environ, "EVENT": event}, capture_output=True).returncode


ALL = ["build-deb", "tests-on-ubuntu-26-04", "build-eira-labwc", "vm-install-acceptance",
       "vm-upgrade-acceptance"]


def test_the_verdict_is_green_only_when_every_job_passed():
    assert _verdict({job: "success" for job in ALL}, "pull_request") == 0
    for job in ALL:
        for bad in ("failure", "cancelled", "skipped"):
            results = {j: "success" for j in ALL} | {job: bad}
            assert _verdict(results, "pull_request") == 1, (job, bad)
    assert _verdict({}, "pull_request") == 1


def test_the_upgrade_may_be_skipped_only_outside_a_pull_request():
    results = {j: "success" for j in ALL} | {"vm-upgrade-acceptance": "skipped"}
    assert _verdict(results, "workflow_dispatch") == 0
    assert _verdict(results | {"vm-install-acceptance": "skipped"}, "workflow_dispatch") == 1


def test_the_tests_on_26_04_run_python_rust_and_ui():
    runs = " ".join(step.get("run", "") for step in WORKFLOW["jobs"]["tests-on-ubuntu-26-04"]["steps"])
    assert "pytest" in runs and "cargo test --locked --workspace" in runs and "npm test" in runs
    assert "alembic" not in runs


# --- the upgrade test (UDVIKLINGSPLAN F0c.7) -----------------------------------------


def test_a_pull_request_builds_the_base_branch_too():
    build = WORKFLOW["jobs"]["build-deb"]
    assert "pull_request" in build["strategy"]["matrix"]["target"]
    assert '"base"' in build["strategy"]["matrix"]["target"]
    steps = {step.get("name"): step for step in build["steps"]}
    assert "base.sha" in steps["Checkout"]["with"]["ref"]
    assert "+ci" in steps["Build Debian package"]["env"]["EIRA_DEB_VERSION_SUFFIX"]


def test_the_upgrade_job_installs_the_base_and_upgrades_to_the_pull_request():
    job = WORKFLOW["jobs"]["vm-upgrade-acceptance"]
    assert job["if"] == "github.event_name == 'pull_request'"
    runs = "\n".join(step.get("run", "") for step in job["steps"])
    assert "--upgrade-deb dist/upgrade/eira-os-core.deb" in runs
    assert "dpkg --compare-versions" in runs
    assert 'grep -q "EIRA-CI mode upgrade from" acceptance.txt' in runs


def test_both_vm_jobs_share_the_same_vm_steps():
    def by_name(job):
        return {s["name"]: s for s in WORKFLOW["jobs"][job]["steps"]}

    fresh, upgrade = by_name("vm-install-acceptance"), by_name("vm-upgrade-acceptance")
    for name in ("Make sure there is disk space", "Install QEMU and enable KVM",
                 "Install EiraOS into a blank disk (UEFI)",
                 "Boot installed system and run acceptance report", "Upload serial logs"):
        assert fresh[name] == upgrade[name], name
    assert "ci-upgrade" in WORKFLOW["jobs"]["vm-upgrade-acceptance"]["env"]["CI_ISO_GLOB"]
    assert "ci-unattended" in WORKFLOW["jobs"]["vm-install-acceptance"]["env"]["CI_ISO_GLOB"]


def test_an_upgrade_restarts_every_daemon_and_the_model():
    # dh_installsystemd --no-start alone (compat 13) adds a preinst that stops
    # every unit on upgrade and never starts them again (the first upgrade
    # run in the VM found all daemons dead). --restart-after-upgrade makes the
    # postinst try-restart the running units instead, with no stop in preinst.
    # The VM check upgrade-daemons-restarted shows it on the running system.
    rules = (ROOT / "packaging" / "debian" / "rules").read_text(encoding="utf-8")
    line = next(line for line in rules.splitlines()
                if line.strip().startswith("dh_installsystemd"))
    assert "--no-start" in line and "--restart-after-upgrade" in line
    assert "--no-restart-after-upgrade" not in line and "--no-stop-on-upgrade" not in line
    control = (ROOT / "packaging" / "debian" / "control").read_text(encoding="utf-8")
    assert "debhelper-compat (= 13)" in control
    units = {p.name for p in (ROOT / "systemd").glob("eira-*.service")}
    policy = json.loads((ROOT / "packaging" / "daemon-policy.json").read_text(encoding="utf-8"))
    assert {f"eira-{d}.service" for d in policy["production_daemons"]} <= units
