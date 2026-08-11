from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class _BaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


class DatabaseSettings(_BaseSettings):
    """PostgreSQL and SQLAlchemy connection-pool settings."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_prefix="POSTGRES_"
    )

    host: str = "localhost"
    port: int = Field(default=5432, ge=1, le=65535)
    user: str = "scenesearch"
    password: SecretStr = SecretStr("scenesearch")
    database: str = Field(
        default="scenesearch",
        validation_alias=AliasChoices("POSTGRES_DB", "POSTGRES_DATABASE"),
    )
    url: str | None = Field(default=None, validation_alias="DATABASE_URL")
    echo: bool = False
    pool_size: int = Field(default=10, ge=1)
    max_overflow: int = Field(default=20, ge=0)
    pool_timeout: float = Field(default=30.0, gt=0)
    pool_recycle: int = Field(default=1800, ge=-1)

    @field_validator("url")
    @classmethod
    def require_asyncpg_driver(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+asyncpg://", 1)
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use the postgresql+asyncpg driver")
        return value


class RedisSettings(_BaseSettings):
    """Redis connection and pool settings."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_prefix="REDIS_"
    )

    host: str = "localhost"
    port: int = Field(default=6379, ge=1, le=65535)
    db: int = Field(default=0, ge=0)
    password: SecretStr | None = None
    url: str | None = Field(default=None, validation_alias="REDIS_URL")
    max_connections: int = Field(default=20, ge=1)
    socket_timeout: float = Field(default=5.0, gt=0)
    socket_connect_timeout: float = Field(default=5.0, gt=0)
    health_check_interval: int = Field(default=30, ge=0)


class CelerySettings(_BaseSettings):
    """Celery broker, result backend, and worker safety limits."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_prefix="CELERY_"
    )

    broker_url: str = "redis://localhost:6379/1"
    result_backend: str = "redis://localhost:6379/2"
    worker_concurrency: int = Field(default=2, ge=1, le=32)
    worker_prefetch_multiplier: int = Field(default=1, ge=1, le=16)
    task_soft_time_limit: int = Field(default=3300, gt=0)
    task_time_limit: int = Field(default=3600, gt=0)
    result_expires: int = Field(default=86400, gt=0)

    @model_validator(mode="after")
    def hard_limit_must_exceed_soft_limit(self) -> CelerySettings:
        if self.task_time_limit <= self.task_soft_time_limit:
            raise ValueError("CELERY_TASK_TIME_LIMIT must exceed CELERY_TASK_SOFT_TIME_LIMIT")
        return self


class MinIOSettings(_BaseSettings):
    """S3-compatible MinIO object-store settings."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_prefix="MINIO_"
    )

    endpoint: str = "localhost:9000"
    access_key: SecretStr = SecretStr("minioadmin")
    secret_key: SecretStr = SecretStr("minioadmin")
    bucket: str = "scenesearch"
    secure: bool = False
    region: str | None = None

    @field_validator("endpoint")
    @classmethod
    def endpoint_must_not_include_scheme(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if value.startswith(("http://", "https://")):
            raise ValueError("MINIO_ENDPOINT must be host:port without an http(s) scheme")
        if not value:
            raise ValueError("MINIO_ENDPOINT cannot be empty")
        return value


class QdrantSettings(_BaseSettings):
    """Qdrant connection and scene-vector settings."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_prefix="QDRANT_"
    )

    host: str = "localhost"
    port: int = Field(default=6333, ge=1, le=65535)
    grpc_port: int = Field(default=6334, ge=1, le=65535)
    https: bool = False
    api_key: SecretStr | None = None
    url: str | None = None
    timeout: float = Field(default=10.0, gt=0)
    prefer_grpc: bool = False
    collection: str = "scenes"
    vector_size: Literal[768] = 768


class AppSettings(_BaseSettings):
    """HTTP application, logging, and model settings."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_prefix="APP_"
    )

    name: str = "SceneSearch-P-081"
    env: Literal["development", "test", "staging", "production"] = "development"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    openai_api_key: SecretStr = Field(default=SecretStr(""), validation_alias="OPENAI_API_KEY")
    model_name: str = Field(default="gpt-4o-mini", validation_alias="MODEL_NAME")
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0, validation_alias="LLM_TEMPERATURE")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                # Keep JSON-array support while NoDecode lets us also accept CSV.
                return json.loads(stripped)
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        return value


class Settings(_BaseSettings):
    """Aggregate of all settings groups used by the application."""

    app: AppSettings = Field(default_factory=AppSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    celery: CelerySettings = Field(default_factory=CelerySettings)
    minio: MinIOSettings = Field(default_factory=MinIOSettings)
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return process-wide validated settings.

    Clear ``get_settings.cache_clear()`` after changing environment variables
    in a test.
    """

    return Settings()


def project_root() -> Path:
    """Return the repository root without relying on the process working directory."""

    return Path(__file__).resolve().parents[2]


__all__ = [
    "AppSettings",
    "CelerySettings",
    "DatabaseSettings",
    "MinIOSettings",
    "QdrantSettings",
    "RedisSettings",
    "Settings",
    "get_settings",
    "project_root",
]
