from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


_MOCK_TRUE_VALUES = {"1", "true", "yes"}


def validate_mock_login_configuration() -> None:
    """Fail closed when mock identity is enabled in a production runtime."""
    environment = os.environ.get("EIRA_ENV", "development").strip().lower()
    mock_enabled = os.environ.get("EIRA_OIDC_MOCK", "").strip().lower() in _MOCK_TRUE_VALUES
    if environment == "production" and mock_enabled:
        raise RuntimeError(
            "EIRA_OIDC_MOCK cannot be enabled when EIRA_ENV=production"
        )


# Run at import time so application startup fails before serving requests.
validate_mock_login_configuration()


class Settings(BaseSettings):
    app_name: str = "EIRA HTTP Dev Bridge"
    version: str = "0.3.0"
    debug: bool = False

    db_path: Path = Path(__file__).resolve().parent.parent / "data" / "eira.db"

    oidc_client_id: str = "eira-dev"
    oidc_redirect_uri: str = "http://localhost:8000/v1/auth/oidc/callback"
    oidc_ui_redirect_uri: str = "http://localhost:5173/"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
