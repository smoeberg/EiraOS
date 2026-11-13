"""Artifact transfers in CI are retried (UDVIKLINGSPLAN F1.4).

GitHub's artifact service failed on 11 November 2026 after a green build.
Every workflow goes through the local retry actions instead of calling
actions/upload-artifact or actions/download-artifact directly.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
ACTIONS = ROOT / ".github" / "actions"


def _steps(workflow: dict):
    for job in workflow.get("jobs", {}).values():
        yield from job.get("steps", [])


def test_no_workflow_calls_the_artifact_actions_directly():
    direct = [
        (path.name, step.get("name"))
        for path in WORKFLOWS
        for step in _steps(yaml.safe_load(path.read_text(encoding="utf-8")))
        if str(step.get("uses", "")).startswith(("actions/upload-artifact", "actions/download-artifact"))
    ]
    assert direct == []


def test_retry_actions_try_three_times_and_overwrite_on_retry():
    for name, inner in (("upload-artifact-retry", "upload"), ("download-artifact-retry", "download")):
        action = yaml.safe_load((ACTIONS / name / "action.yml").read_text(encoding="utf-8"))
        steps = action["runs"]["steps"]
        attempts = [s for s in steps if str(s.get("uses", "")).startswith(f"actions/{inner}-artifact@")]
        assert len(attempts) == 3, name
        assert attempts[0]["continue-on-error"] is True
        assert attempts[1]["continue-on-error"] is True
        assert "continue-on-error" not in attempts[2]  # the last attempt fails the job
        if inner == "upload":
            assert all(a["with"].get("overwrite") is True for a in attempts[1:])


def test_jobs_with_sparse_checkout_include_the_local_actions():
    for path in WORKFLOWS:
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job_name, job in workflow.get("jobs", {}).items():
            steps = job.get("steps", [])
            if not any(str(s.get("uses", "")).startswith("./.github/actions/") for s in steps):
                continue
            for step in steps:
                sparse = (step.get("with") or {}).get("sparse-checkout")
                if str(step.get("uses", "")).startswith("actions/checkout") and sparse:
                    assert ".github/actions" in sparse, (path.name, job_name)
