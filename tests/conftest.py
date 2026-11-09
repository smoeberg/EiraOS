"""Shared test configuration for explicit OIDC mock-login use in tests."""

import os

# Mock authentication is only enabled explicitly for the test process. Tests
# that verify fail-closed behavior must remove this variable with monkeypatch.
os.environ["EIRA_ENV"] = "development"
os.environ["EIRA_OIDC_MOCK"] = "1"


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _human_caller():
    """Gate calls in tests act as a human user on the socket, as the IPC layer
    sets it in production. Tests about callers override it explicitly."""
    from app.gate.caller import acting_as
    from tests.callers import HUMAN

    with acting_as(HUMAN):
        yield
