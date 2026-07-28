from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


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
