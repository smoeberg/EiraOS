"""Shared test configuration for explicit OIDC mock-login use in tests."""

import os

# Mock authentication is only enabled explicitly for the test process. Tests
# that verify fail-closed behavior must remove this variable with monkeypatch.
os.environ["EIRA_ENV"] = "development"
os.environ["EIRA_OIDC_MOCK"] = "1"


import pytest  # noqa: E402

from tests.tpm import other_tpm, tpm  # noqa: E402, F401 (software TPM fixtures, EIRA-CONTEXT §5.0)


@pytest.fixture(autouse=True)
def _human_caller():
    """Gate calls in tests act as a human user on the socket, as the IPC layer
    sets it in production. Tests about callers override it explicitly."""
    from app.gate.caller import acting_as
    from tests.callers import HUMAN

    with acting_as(HUMAN):
        yield


@pytest.fixture(autouse=True)
def _consent_key_store(tmp_path, monkeypatch):
    """Each test gets its own consent-key store. Tests run on whatever
    filesystem tmp_path is on, so the tmpfs requirement is waived here;
    tests/test_consent_keys_ram_only.py checks it with the waiver removed."""
    monkeypatch.setenv("EIRA_CONSENT_KEY_DB", str(tmp_path / "consent-keys.db"))
    monkeypatch.setenv("EIRA_CONSENT_KEYS_ALLOW_DISK", "1")
