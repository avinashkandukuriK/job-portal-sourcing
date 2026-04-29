"""Application settings loaded from environment / .env file."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""           # publishable (read) key
    supabase_service_key: str = ""   # service-role (write) key

    # Free / public APIs
    github_token: str = ""
    stackexchange_key: str = ""

    # Paid adapter keys (empty = adapter disabled)
    apollo_api_key: str = ""
    proxycurl_api_key: str = ""
    indeed_publisher_id: str = ""
    dice_api_key: str = ""
    monster_api_key: str = ""
    ziprecruiter_api_key: str = ""

    # App
    app_env: str = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def has_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
