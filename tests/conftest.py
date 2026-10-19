"""Shared test configuration for explicit OIDC mock-login use in tests."""

import os

# Mock authentication is only enabled explicitly for the test process. Tests
# that verify fail-closed behavior must remove this variable with monkeypatch.
os.environ["EIRA_ENV"] = "development"
os.environ["EIRA_OIDC_MOCK"] = "1"
