from __future__ import annotations

from pathlib import Path

from app.daemons.runner import DAEMON_NAMES, REGISTRARS

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_all_ten_sprint_deliverable_boundaries_exist() -> None:
    required = {
        "sprint_1_2": ["app/core/state.py", "app/daemons/stated.py", "app/ipc/transport.py"],
        "sprint_3_4": ["app/veritas/layer2_qeaa.py", "app/core/cel_evaluator.py"],
        "sprint_5_6": ["app/fleet/e2ee.py", "crates/eira-core/src/ffi.rs", "android/app/build.gradle.kts"],
        "sprint_7_8": ["ui/src/components/SpatialCanvas.tsx", "crates/eira-ipc/src/shm.rs"],
        "sprint_9": ["packaging/debian/control", "scripts/build_iso.sh"],
        "sprint_10": ["app/auth/production_cert_verifier.py", "scripts/release_rc1.sh"],
    }
    missing = {
        sprint: [path for path in paths if not (REPO_ROOT / path).is_file()]
        for sprint, paths in required.items()
    }
    assert not {sprint: paths for sprint, paths in missing.items() if paths}


def test_every_declared_daemon_has_runtime_service_and_profile() -> None:
    expected = {"stated", "identityd", "fleetd", "veritasd", "intentd", "graphd"}
    assert set(DAEMON_NAMES) == expected
    assert set(REGISTRARS) == expected
    for daemon in expected:
        assert (REPO_ROOT / "systemd" / f"eira-{daemon}.service").is_file()
        assert (REPO_ROOT / "packaging" / "apparmor" / f"usr.bin.eira-{daemon}").is_file()


def test_release_gate_has_no_unverified_bypass() -> None:
    release = (REPO_ROOT / "scripts" / "release_rc1.sh").read_text(encoding="utf-8")
    assert "--skip-tests)" not in release
    assert "EIRA_RELEASE_GATE=1" in release
    assert "gpg --batch --verify" in release
    assert "sha3_256" in release
    assert "cargo test --workspace" in release
    assert "gradle --project-dir android test" in release
    assert "apparmor_parser" in release


def test_production_state_database_has_one_daemon_owner() -> None:
    stated = (REPO_ROOT / "systemd" / "eira-stated.service").read_text(encoding="utf-8")
    fleet = (REPO_ROOT / "app" / "daemons" / "fleetd.py").read_text(encoding="utf-8")
    assert "EIRA_STATE_DB=/data/eira.db" in stated
    assert "store=RpcStateStore()" in fleet
    assert 'StateStore(os.environ.get("EIRA_STATE_DB"' not in fleet


def test_pilot_security_guarantees_are_explicit() -> None:
    ipc_auth = (REPO_ROOT / "app" / "ipc" / "auth.py").read_text(encoding="utf-8")
    fleet_unit = (REPO_ROOT / "systemd" / "eira-fleetd.service").read_text(
        encoding="utf-8"
    )
    state = (REPO_ROOT / "app" / "core" / "state.py").read_text(encoding="utf-8")
    audit = (REPO_ROOT / "app" / "core" / "audit.py").read_text(encoding="utf-8")
    certificates = (
        REPO_ROOT / "app" / "auth" / "production_cert_verifier.py"
    ).read_text(encoding="utf-8")
    assert "hmac.compare_digest" in ipc_auth
    assert "EIRA_FLEET_WS_HOST=127.0.0.1" in fleet_unit
    assert "hashlib.sha3_256" in state
    assert "previous_audit_hash" in audit
    assert '"mitid_erhverv", "eudi_wallet"' in certificates
