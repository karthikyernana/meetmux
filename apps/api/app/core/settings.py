"""PlanGuard application settings."""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, PostgresDsn, RedisDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_name: str = "PlanGuard"
    app_version: str = "0.1.0"
    environment: Literal["development", "production", "test"] = "development"
    debug: bool = False

    # Database (PlanGuard app DB)
    database_url: PostgresDsn = Field(
        default="postgresql+psycopg://planguard:planguard@localhost:5432/planguard"
    )

    # Redis / RQ
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")

    # Security
    app_encryption_key: str = Field(
        default="CHANGE_ME_32_BYTE_BASE64_KEY_XXXX",
        description="Fernet key for encrypting DB credentials at rest",
    )
    allowed_origins_raw: Any = Field(
        default=["http://localhost:5173"],
        alias="allowed_origins",
    )

    @property
    def allowed_origins(self) -> list[str]:
        val = self.allowed_origins_raw
        if isinstance(val, str):
            val = val.strip()
            if val.startswith("[") and val.endswith("]"):
                import json
                try:
                    res = json.loads(val)
                    if isinstance(res, list):
                        return [str(x) for x in res]
                except Exception:
                    pass
            return [x.strip() for x in val.split(",") if x.strip()]
        if isinstance(val, list):
            return [str(x) for x in val]
        return ["http://localhost:5173"]

    # AI — all optional / disabled by default
    llm_enabled: bool = False
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"

    jev_enabled: bool = False
    typesafe_api_key: str = ""

    # Analysis limits (configurable, not magic numbers)
    max_candidates_per_query: int = 8
    max_index_columns: int = 3

    # Workload limits
    max_query_fingerprints_per_snapshot: int = 10_000
    max_high_priority_queries: int = 100

    # Statement timeout for analysis connections (ms)
    analysis_statement_timeout_ms: int = 30_000

    @model_validator(mode="after")
    def _check_encryption_key(self) -> "Settings":
        if self.environment == "production" and self.app_encryption_key.startswith("CHANGE_ME"):
            raise ValueError("APP_ENCRYPTION_KEY must be set in production")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
