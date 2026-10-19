from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    hubspot_access_token: str = ""
    hubspot_portal_id: str = ""
    hubspot_base_url: str = "https://api.hubapi.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()
