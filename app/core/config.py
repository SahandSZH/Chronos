from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Stay On Track API"
    api_v1_prefix: str = "/api/v1"

    database_url: str

    # Keep a non-empty default so Render Web Service can boot even if user forgets this env var.
    # For production, set JWT_SECRET_KEY explicitly in Render.
    jwt_secret_key: str = "change-this-jwt-secret-in-render"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    default_timezone: str = "America/Toronto"
    calendar_locale: str = "en-CA"

    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str | None = None
    google_scopes: list[str] = Field(
        default_factory=lambda: ["https://www.googleapis.com/auth/calendar.events"]
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        if isinstance(value, list):
            return value
        raise ValueError("Invalid CORS origins format.")

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("DATABASE_URL must be a string.")

        raw = value.strip()

        # Allow pasting Neon CLI/psql format:
        # psql 'postgresql://...'
        if raw.lower().startswith("psql "):
            raw = raw[5:].strip()

        if (raw.startswith("'") and raw.endswith("'")) or (
            raw.startswith('"') and raw.endswith('"')
        ):
            raw = raw[1:-1].strip()

        # SQLAlchemy engine in this app uses psycopg driver.
        if raw.startswith("postgresql://"):
            raw = raw.replace("postgresql://", "postgresql+psycopg://", 1)
        elif raw.startswith("postgres://"):
            raw = raw.replace("postgres://", "postgresql+psycopg://", 1)

        return raw

    @field_validator("google_scopes", mode="before")
    @classmethod
    def _parse_google_scopes(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [scope.strip() for scope in value.split(",") if scope.strip()]
        if isinstance(value, list):
            return value
        raise ValueError("Invalid GOOGLE_SCOPES format.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
