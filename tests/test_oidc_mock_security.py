from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.auth.oidc import claims_from_mock_login, load_oidc_config
from app.config import validate_mock_login_configuration


def test_mock_login_is_disabled_by_default_without_client_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OIDC_CLIENT_ID", raising=False)
    monkeypatch.delenv("EIRA_OIDC_MOCK", raising=False)
    monkeypatch.setenv("EIRA_ENV", "development")

    assert load_oidc_config().mock_enabled is False


@pytest.mark.parametrize("flag", ["1", "true", "yes"])
def test_mock_login_requires_and_accepts_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch, flag: str
) -> None:
    monkeypatch.setenv("EIRA_ENV", "development")
    monkeypatch.setenv("EIRA_OIDC_MOCK", flag)

    assert load_oidc_config().mock_enabled is True


def test_mock_login_rejected_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EIRA_ENV", "production")
    monkeypatch.setenv("EIRA_OIDC_MOCK", "1")

    with pytest.raises(RuntimeError, match="cannot be enabled"):
        validate_mock_login_configuration()
    with pytest.raises(RuntimeError, match="cannot be enabled"):
        load_oidc_config()


def test_production_startup_fails_if_mock_login_is_enabled() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repo_root)
    environment["EIRA_ENV"] = "production"
    environment["EIRA_OIDC_MOCK"] = "true"

    result = subprocess.run(
        [sys.executable, "-c", "import app.auth.oidc"],
        cwd=repo_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode != 0
    assert "EIRA_OIDC_MOCK cannot be enabled" in result.stderr


def test_mock_claims_ignore_untrusted_tenant_and_identity_claims() -> None:
    claims = claims_from_mock_login(
        {
            "email": "person@example.com",
            "tenant_id": "attacker-tenant",
            "tid": "attacker-tid",
            "org_unit": "Privileged Org",
            "tenant_name": "Privileged Tenant",
            "sub": "victim",
            "idp": "entra",
            "assurance_level": "idp_authenticated",
        }
    )

    assert claims["tenant_id"] == "mock-tenant"
    assert claims["org_unit"] == "Mock"
    assert claims["sub"] == "person@example.com"
    assert claims["idp"] == "entra_mock"
    assert claims["assurance_level"] == "mock_authenticated"
