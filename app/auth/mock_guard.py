"""Fail closed when mock identity is enabled in production.

Kept free of third-party imports: identityd loads it on an installed system,
where only the packages in debian/control exist (pydantic-settings does not).
"""

from __future__ import annotations

import os

_MOCK_TRUE_VALUES = {"1", "true", "yes"}


def validate_mock_login_configuration() -> None:
    environment = os.environ.get("EIRA_ENV", "development").strip().lower()
    mock_enabled = os.environ.get("EIRA_OIDC_MOCK", "").strip().lower() in _MOCK_TRUE_VALUES
    if environment == "production" and mock_enabled:
        raise RuntimeError("EIRA_OIDC_MOCK cannot be enabled when EIRA_ENV=production")
