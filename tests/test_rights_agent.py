"""Applying the bundle's default rights set (EIRA-RIGHTS-SET-1.0 §5)."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

import pytest

from app.gate.policy import REGISTRY
from app.rights import agent, contract, fleet_api
from app.rights.cache import RightsCache

ROOT = Path(__file__).resolve().parents[1]
# Builds in the past (a build in the future is "not yet valid", correctly).
OLDER = int(time.time()) - 7200
NEWER = OLDER + 3600


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    out = tmp_path / "bundle"
    monkeypatch.setenv("EIRA_RIGHTS_BUILD_EPOCH", str(OLDER))
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_default_rights.py"), str(out)],
        check=True, capture_output=True,
    )
    monkeypatch.setattr(fleet_api, "ENROLLMENT_PATH", tmp_path / "no-enrollment.json")
    return out


def test_built_default_set_verifies_and_is_private_machine(bundle):
    doc = json.loads((bundle / "default.json").read_text())
    assert (doc["kind"], doc["tenant_id"], doc["device_id"]) == ("default", "unmanaged", "*")
    assert doc["version"] == OLDER
    issued, expires = contract._ts(doc["issued_at"]), contract._ts(doc["expires_at"])
    assert expires - issued <= contract.MAX_TTL["default"]
    keys = {a for g in doc["grants"] for a in g["actions"]}
    assert keys == set(contract.action_keys(REGISTRY))  # nothing outside the gate
    anchors = json.loads((bundle / "anchors.json").read_text())["anchors"]
    assert [a["kind"] for a in anchors.values()] == ["default"]


def test_changelog_date_does_not_fix_the_version(tmp_path, monkeypatch):
    """dpkg-buildpackage exports SOURCE_DATE_EPOCH from debian/changelog."""
    monkeypatch.delenv("EIRA_RIGHTS_BUILD_EPOCH", raising=False)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1785578400")  # changelog: 2026-08-01
    out = tmp_path / "b"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_default_rights.py"), str(out)], check=True)
    assert json.loads((out / "default.json").read_text())["version"] > 1785578400 + 86400


def test_build_key_is_never_written(bundle):
    for path in bundle.iterdir():
        text = path.read_text()
        assert "PRIVATE" not in text and "seed" not in text
    assert sorted(p.name for p in bundle.iterdir()) == ["anchors.json", "default.json"]


def test_apply_default_installs_then_is_idempotent(bundle, tmp_path, capsys):
    cache = RightsCache(tmp_path / "rights")
    assert agent.apply_default(bundle, cache) == 0
    assert json.loads(capsys.readouterr().out)["result"] == "applied"
    assert agent.apply_default(bundle, cache) == 0
    assert json.loads(capsys.readouterr().out)["result"] == "noop"
    from datetime import datetime, timezone

    active = cache.current(datetime.now(timezone.utc))
    assert active is not None and active.owner_admin


def test_newer_package_supersedes_older(bundle, tmp_path, monkeypatch, capsys):
    cache = RightsCache(tmp_path / "rights")
    assert agent.apply_default(bundle, cache) == 0
    newer = tmp_path / "newer"
    monkeypatch.setenv("EIRA_RIGHTS_BUILD_EPOCH", str(NEWER))
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_default_rights.py"), str(newer)], check=True
    )
    assert agent.apply_default(newer, cache) == 0
    assert cache.active_meta().version == NEWER
    # and the older package cannot come back
    capsys.readouterr()
    assert agent.apply_default(bundle, cache) == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "version_rollback"


def test_enrolled_device_does_not_take_the_default_set(bundle, tmp_path, monkeypatch, capsys):
    enrollment = tmp_path / "enrollment.json"
    enrollment.write_text(json.dumps({
        "eira_enrollment": "2", "tenant_id": "kk", "device_id": "dev-1",
        "fleet_url": "https://fleet.kk.example",
        "rights_roots": {"kk-root-1": {"public_key": "A" * 43, "not_after": "2036-01-01T00:00:00Z"}},
    }))
    monkeypatch.setattr(fleet_api, "ENROLLMENT_PATH", enrollment)
    cache = RightsCache(tmp_path / "rights")
    assert agent.apply_default(bundle, cache) == 0
    assert json.loads(capsys.readouterr().out)["result"] == "not_applicable"
    assert cache.active_meta() is None


def test_malformed_enrollment_never_falls_back_to_private(bundle, tmp_path, monkeypatch, capsys):
    enrollment = tmp_path / "enrollment.json"
    enrollment.write_text(json.dumps({"tenant_id": "kk", "device_id": "dev-1"}))  # no anchors
    monkeypatch.setattr(fleet_api, "ENROLLMENT_PATH", enrollment)
    cache = RightsCache(tmp_path / "rights")
    assert agent.apply_default(bundle, cache) == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "enrollment_malformed"
    assert cache.active_meta() is None


def test_tampered_bundle_is_rejected_and_nothing_changes(bundle, tmp_path, capsys):
    cache = RightsCache(tmp_path / "rights")
    raw = (bundle / "default.json").read_text().replace('"scope":"device:local"', '"scope":"obj:sag:*"')
    (bundle / "default.json").write_text(raw)
    assert agent.apply_default(bundle, cache) == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "bad_signature"
    assert cache.active_meta() is None


def test_missing_bundle(tmp_path, capsys):
    assert agent.apply_default(tmp_path / "nothing", RightsCache(tmp_path / "r")) == 2


def test_clock_set_back_cannot_reapply_an_expired_set(bundle, tmp_path):
    """The agent judges sets at max(wall clock, the cache's high-water mark)."""
    cache = RightsCache(tmp_path / "rights")
    doc = json.loads((bundle / "default.json").read_text())
    expires = contract._ts(doc["expires_at"])
    raw = (bundle / "default.json").read_bytes()
    anchors = agent.load_anchors(bundle / "anchors.json")
    # The device has already seen a time after expiry …
    assert agent.apply(raw, anchors=anchors, device=contract.Device(False), cache=cache,
                       registry=REGISTRY, wall_now=contract._ts(doc["issued_at"])).ok
    cache.current(expires + timedelta(days=1))
    cache._write("active.json", b"")  # active set lost
    state = json.loads((cache.directory / "state.json").read_text())
    state["version"] = 1
    cache._write("state.json", json.dumps(state).encode())
    # … then the clock goes back to before expiry: still expired.
    verdict = agent.apply(raw, anchors=anchors, device=contract.Device(False), cache=cache,
                          registry=REGISTRY, wall_now=contract._ts(doc["issued_at"]))
    assert verdict.reason == "expired"


def test_cli_usage():
    assert agent.main(["nonsense"]) == 64


@pytest.mark.parametrize("module", ["app.rights.agent", "app.rights.cache", "app.gate"])
def test_entry_points_import_alone(module):
    """eira-rights-apply starts with nothing imported; a cycle between the
    gate and the rights cache only shows up then (found in the VM)."""
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"], cwd=ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_cache_directory_is_usable_under_the_daemon_umask(bundle, tmp_path):
    """systemd units use UMask=0117; mkdir(0o700) alone gives 0600."""
    import os
    import stat

    old = os.umask(0o117)
    try:
        cache = RightsCache(tmp_path / "rights")
        assert agent.apply_default(bundle, cache) == 0
    finally:
        os.umask(old)
    assert stat.S_IMODE((tmp_path / "rights").stat().st_mode) == 0o700
