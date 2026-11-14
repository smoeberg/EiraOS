"""SECURITY.md and secret scanning (UDVIKLINGSPLAN §4 nr. 2; the repository is public)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_security_policy_says_how_to_report_and_what_to_expect():
    text = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "security/advisories/new" in text
    assert "5 arbejdsdage" in text and "90 dage" in text
    for link in re.findall(r"\]\(((?!https?:)[^)#]+)", text):
        assert (ROOT / link).exists(), link


def test_ci_scans_all_history_with_a_verified_gitleaks():
    jobs = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))["jobs"]
    job = jobs["secret-scan"]
    assert job["steps"][0]["with"]["fetch-depth"] == 0
    runs = " ".join(step.get("run", "") for step in job["steps"])
    assert "sha256sum -c" in runs
    assert '--log-opts="--all"' in runs and "--config .gitleaks.toml" in runs
    assert (ROOT / ".gitleaks.toml").is_file()
