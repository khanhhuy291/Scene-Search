from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_INSECURE_DEFAULT_AUTH_SECRET = (
    "scenesearch-insecure-jwt-secret-key-change-in-production-min32chars"
)


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
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="POSTGRES_",
        populate_by_name=True,
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
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="CELERY_",
        populate_by_name=True,
    )

    broker_url: str = Field(
        default="redis://localhost:6379/1",
        validation_alias=AliasChoices("CELERY_BROKER_URL", "REDIS_URL"),
    )
    result_backend: str = Field(
        default="redis://localhost:6379/2",
        validation_alias=AliasChoices("CELERY_RESULT_BACKEND", "REDIS_URL"),
    )
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
    # ADR-0003: originals and servable derivatives live in separate buckets, so
    # the privacy guarantee rests on which store an object is in rather than on
    # request-time code remembering to check.
    raw_bucket: str = "scenesearch-raw"
    derived_bucket: str = "scenesearch-derived"
    # Presigned URL lifetime for derived assets.
    url_ttl_seconds: int = Field(default=3600, ge=60, le=604800)
    secure: bool = False
    region: str | None = None

    # Where the *indexed* keyframe thumbnails and clips live, when that is not
    # this deployment's own store. The search index and the media it references
    # are produced together by the embedding pipeline, so while this service reads
    # someone else's index it must read their objects too. Kept separate from
    # ``endpoint`` so that attaching to an external index does not silently
    # redirect this deployment's own ingestion writes into it.
    scene_media_endpoint: str | None = None
    scene_media_bucket: str = "scenesearch"
    # The public console host (minio.viettech.fit) is not the S3 API. When this
    # is true, media is fetched through the console REST API instead of the SDK.
    scene_media_console: bool = False
    scene_media_secure: bool = False

    @field_validator("scene_media_endpoint")
    @classmethod
    def media_endpoint_must_not_include_scheme(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().rstrip("/")
        if not value:
            return None
        if value.startswith("https://"):
            value = value[len("https://") :]
        elif value.startswith("http://"):
            value = value[len("http://") :]
        value = value.strip().rstrip("/")
        return value or None

    @model_validator(mode="after")
    def buckets_must_be_distinct(self) -> MinIOSettings:
        if self.raw_bucket == self.derived_bucket:
            raise ValueError(
                "MINIO_RAW_BUCKET and MINIO_DERIVED_BUCKET must differ; sharing one "
                "bucket would make originals presignable"
            )
        return self

    @field_validator("endpoint")
    @classmethod
    def endpoint_must_not_include_scheme(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if value.startswith("https://"):
            value = value[len("https://") :]
        elif value.startswith("http://"):
            value = value[len("http://") :]
        value = value.strip().rstrip("/")
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
    collection: str = "Scences"
    # ADR-0001: not pinned to one encoder. Points carry ``model_version`` so a
    # dimension change is a re-index rather than a schema migration.
    vector_size: int = Field(default=768, ge=64, le=4096)
    hnsw_ef_search: int = Field(default=128, ge=16, le=1024)
    # Named-vector collections are read-only unless deployment explicitly opts in
    write_vector_name: str = ""
    allow_named_vector_writes: bool = False


class MLSettings(_BaseSettings):
    """Embedding-model and inference-device settings (ADR-0001)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="ML_",
        populate_by_name=True,
    )

    # Primary multimodal embedding model (Qwen 2048d, or SigLIP 768d).
    encoder_name: str = "ViT-B-16-SigLIP"
    encoder_pretrained: str = "webli"
    # Stamped onto every Qdrant point so two encoders can coexist during a
    # re-index and be filtered apart at query time.
    model_version: str = "siglip-b16-224-v1"
    # Optional remote URL or model identifier for Qwen3-VL-Embedding service
    qwen_embedding_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("QWEN_EMBEDDING_URL", "ML_QWEN_EMBEDDING_URL"),
    )
    qwen_embedding_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("QWEN_EMBEDDING_API_KEY", "ML_QWEN_EMBEDDING_API_KEY"),
    )
    qwen_embedding_timeout: float = Field(
        default=120.0,
        gt=0,
        validation_alias=AliasChoices("QWEN_EMBEDDING_TIMEOUT", "ML_QWEN_EMBEDDING_TIMEOUT"),
    )
    qwen_model_name: str = "Qwen/Qwen3-VL-Embedding-2B"
    # ``auto`` resolves to mps, then cuda, then cpu. Docker on macOS cannot
    # reach MPS, so the worker is expected to run natively on the host.
    device: Literal["auto", "mps", "cuda", "cpu"] = "auto"
    # fp32 by default: MPS half precision has known numerical gaps in some
    # transformer operators, and the corpus is small enough not to need fp16.
    dtype: Literal["float32", "float16", "bfloat16"] = "float32"
    batch_size: int = Field(default=64, ge=1, le=512)
    image_size: int = Field(default=224, ge=64, le=1024)
    num_workers: int = Field(default=2, ge=0, le=16)

    @field_validator("qwen_embedding_url", mode="before")
    @classmethod
    def validate_qwen_embedding_url(cls, value: object) -> object:
        """Reject pasted Markdown links instead of silently using local inference."""
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        url = value.strip()
        if not url:
            return None
        if any(character in url for character in "[]()"):
            raise ValueError("QWEN_EMBEDDING_URL must be a plain URL, not a Markdown link")
        if not url.startswith(("http://", "https://")):
            raise ValueError("QWEN_EMBEDDING_URL must start with http:// or https://")
        return url.rstrip("/")


class VideoSettings(_BaseSettings):
    """Decoding, sampling, and preview-encoding settings (ADR-0004)."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_prefix="VIDEO_"
    )

    # Frames per second to sample for embedding. The selected corpus contract
    # uses a 5 fps annotation cadence; lower values subsample it.
    sample_fps: float = Field(default=1.0, gt=0, le=60)
    sampling_max_gap_sec: float = Field(default=2.0, gt=0, le=60)
    sampling_ssim_threshold: float = Field(default=0.98, ge=0, le=1)
    # Drop a frame whose cosine similarity to the last kept frame exceeds this.
    # Driving footage is highly redundant when the vehicle is stopped, and this
    # is the single largest lever on index cost.
    dedup_threshold: float = Field(default=0.98, ge=0.5, le=1.0)
    # Set to 1.0 to disable deduplication entirely.
    dedup_enabled: bool = True

    # Segment aggregation: consecutive frames are mean-pooled into clip-level
    # vectors so a query can return a watchable span rather than a still.
    segment_seconds: float = Field(default=5.0, gt=0, le=60)
    segment_gap_tolerance_s: float = Field(default=1.0, ge=0, le=10)

    # Full-video derived playback preserves source imagery/cadence. Encoding
    # settings apply to the non-H.264 fallback; preview_fps is a legacy option.
    preview_codec: str = "libx264"
    preview_crf: int = Field(default=28, ge=0, le=51)
    preview_max_edge: int = Field(default=1280, ge=128, le=3840)
    preview_fps: float = Field(default=5.0, gt=0, le=60)

    # Decode limits, enforced before any work is queued.
    max_duration_s: float = Field(default=600.0, gt=0)
    max_pixels: int = Field(default=4096 * 2160, gt=0)

    @model_validator(mode="after")
    def segment_must_span_multiple_samples(self) -> VideoSettings:
        # A segment shorter than one sample interval would contain at most one
        # frame, which makes segment granularity indistinguishable from frame
        # granularity while still doubling the index size.
        if self.segment_seconds < 2.0 / self.sample_fps:
            raise ValueError(
                f"VIDEO_SEGMENT_SECONDS={self.segment_seconds} is too short to hold two "
                f"frames at VIDEO_SAMPLE_FPS={self.sample_fps}"
            )
        return self


class DatasetSettings(_BaseSettings):
    """Local corpus layout selected by ADR-0005."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_prefix="DATASET_"
    )

    name: str = "driving-video-object-tracking"
    split: str = "val"
    # Populated by the corpus converter; ingestion consumes only this manifest
    # contract and never depends on the source dataset's directory layout.
    root: Path = Path("data/driving-video-object-tracking")
    manifest_name: str = "manifest.jsonl"
    thumbnail_max_edge: int = Field(default=512, ge=64, le=2048)
    thumbnail_quality: int = Field(default=80, ge=1, le=100)

    @property
    def manifest_path(self) -> Path:
        return self.root / self.manifest_name


class SearchSettings(_BaseSettings):
    """Retrieval thresholds, measured against the indexed corpus.

    These are calibration constants, not preferences, which is why they live here
    with their measurement recorded rather than inline in the engine. Re-measure
    them when the encoder or the corpus changes: a floor calibrated on dashcam
    footage says nothing about a corpus of kitchen footage.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_prefix="SEARCH_"
    )

    # Minimum SigLIP cosine for a keyframe to be a plausible answer at all.
    #
    # Without a floor, nearest-neighbour search always returns its k nearest
    # neighbours, so a query for something the corpus does not contain returns the
    # least-unrelated footage with no signal that it is unrelated -- "spiderman"
    # answered with several hundred dashcam clips.
    #
    # 0.09 is where the two populations separate on this index, measured over 22
    # in-domain and 14 out-of-domain queries (scripts/calibrate_floor.py, recorded
    # in SearchSettings / SRS NFR-PERF-06): every in-domain query peaked at 0.096 or above, every
    # out-of-domain one at 0.088 or below. The value sits in that gap, nearer the
    # bottom of it, because a thin result beats wrongly reporting an empty corpus.
    #
    # Note this is an *absolute* cutoff on purpose. Scoring each query against a
    # random background sample was tried first and is actively misleading here:
    # out-of-domain queries score *further* above their background than in-domain
    # ones do, because nothing in the corpus resembles them, so their similarity
    # distribution is narrow and any weak top hit looks like an outlier.
    visual_floor: float = Field(default=0.09, ge=0.0, le=1.0)
    qwen_visual_floor: float = Field(default=0.02, ge=0.0, le=1.0)
    caption_floor: float = Field(default=0.0, ge=0.0, le=1.0)

    # Whether a concept named in the query must be positively confirmed by the
    # caption, rather than merely not contradicted by it.
    strict_concepts: bool = False

    # Primary search retrieval mode: "hybrid", "qwen", or "siglip".
    mode: Literal["hybrid", "siglip", "qwen", "visual", "caption"] = Field(
        default="hybrid",
        validation_alias=AliasChoices("SEARCH_MODE", "SEARCH_DEFAULT_MODE"),
    )
    visual_vector: str = "siglip"
    caption_vector: str = ""

    # Cadence used to recover a timestamp when the payload has a frame index
    # (``frame_id`` / ``frame_00034.jpg``) but no ``timestamp_sec``. The live
    # Viettech collection is sampled at the MOT annotation rate.
    keyframe_fps: float = Field(default=5.0, gt=0, le=60)

    # Tri-Tier Adaptive Agentic Search controls
    agentic_enabled: bool = False
    hyde_enabled: bool = True
    domain_guardrail_enabled: bool = True
    max_reflection_loops: int = Field(default=1, ge=0, le=3)

    # Cross-encoder reranking controls
    rerank_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("SEARCH_RERANK_ENABLED", "RERANK_ENABLED"),
    )
    rerank_top_k: int = Field(
        default=30,
        ge=1,
        le=200,
        validation_alias=AliasChoices("SEARCH_RERANK_TOP_K", "RERANK_TOP_K"),
    )
    reranker_model_name: str = Field(
        default="Qwen/Qwen3-VL-Reranker-2B",
        validation_alias=AliasChoices("ML_RERANKER_NAME", "RERANKER_MODEL_NAME"),
    )
    reranker_device: Literal["auto", "cuda", "cpu", "mps"] = Field(
        default="auto",
        validation_alias=AliasChoices("RERANKER_DEVICE", "ML_RERANKER_DEVICE"),
    )


class LLMSettings(_BaseSettings):
    """OpenAI-compatible LLM service settings for Agentic Search (HyDE & Routing)."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_prefix="LLM_"
    )

    api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("LLM_API_KEY", "OPENAI_API_KEY"),
    )
    base_url: str = Field(
        default="https://api.openai.com/v1",
        validation_alias=AliasChoices("LLM_BASE_URL", "OPENAI_BASE_URL"),
    )
    model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("LLM_MODEL", "OPENAI_MODEL"),
    )
    timeout: float = Field(default=10.0, gt=0.1, le=60.0)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)


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

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    # .env often has APP_CORS_ORIGINS=[http://localhost:5173] without
                    # quotes. That is not JSON; treat the inside as CSV.
                    stripped = stripped.strip("[]")
            return [origin.strip().strip("\"'") for origin in stripped.split(",") if origin.strip()]
        return value


class AuthSettings(_BaseSettings):
    """JWT authentication and authorization settings loaded from environment."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_prefix="AUTH_"
    )

    secret_key: SecretStr = Field(
        default=SecretStr(_INSECURE_DEFAULT_AUTH_SECRET),
        validation_alias=AliasChoices("AUTH_SECRET_KEY", "SECRET_KEY", "JWT_SECRET_KEY"),
        description="256-bit secret key used to sign and verify JWT tokens",
    )
    algorithm: str = Field(
        default="HS256",
        validation_alias=AliasChoices("AUTH_ALGORITHM", "JWT_ALGORITHM"),
    )
    access_token_expire_minutes: int = Field(
        default=60 * 24,
        ge=1,
        validation_alias=AliasChoices(
            "AUTH_ACCESS_TOKEN_EXPIRE_MINUTES", "ACCESS_TOKEN_EXPIRE_MINUTES"
        ),
    )
    refresh_token_expire_days: int = Field(
        default=7,
        ge=1,
        validation_alias=AliasChoices(
            "AUTH_REFRESH_TOKEN_EXPIRE_DAYS", "REFRESH_TOKEN_EXPIRE_DAYS"
        ),
    )

    @field_validator("secret_key", mode="before")
    @classmethod
    def require_valid_secret_key(cls, value: object) -> object:
        if isinstance(value, SecretStr):
            raw = value.get_secret_value()
        elif isinstance(value, str):
            raw = value
        else:
            return value

        raw = raw.strip()
        if not raw:
            raise ValueError("AUTH_SECRET_KEY cannot be empty")
        if len(raw) < 32:
            raise ValueError(
                f"AUTH_SECRET_KEY must be at least 32 characters long for security (got {len(raw)})"
            )
        return raw


class Settings(_BaseSettings):
    """Aggregate of all settings groups used by the application."""

    app: AppSettings = Field(default_factory=AppSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    celery: CelerySettings = Field(default_factory=CelerySettings)
    minio: MinIOSettings = Field(default_factory=MinIOSettings)
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    ml: MLSettings = Field(default_factory=MLSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    video: VideoSettings = Field(default_factory=VideoSettings)
    dataset: DatasetSettings = Field(default_factory=DatasetSettings)

    @model_validator(mode="after")
    def encoder_dimension_must_match_collection(self) -> Settings:
        # Catching this at startup is far cheaper than discovering it as a
        # Qdrant upsert rejection midway through an index run.
        known_dimensions = {
            "ViT-B-16-SigLIP": 768,
            "ViT-B-16-SigLIP-256": 768,
            "ViT-B-16-SigLIP-384": 768,
            "ViT-B-16-SigLIP-512": 768,
            "ViT-L-16-SigLIP-256": 1024,
            "ViT-L-16-SigLIP-384": 1024,
            "ViT-SO400M-14-SigLIP": 1152,
            "ViT-SO400M-14-SigLIP-384": 1152,
            "Qwen/Qwen3-VL-Embedding-2B": 2048,
            "Qwen3-VL-Embedding-2B": 2048,
        }
        expected = known_dimensions.get(self.ml.encoder_name)
        if (
            expected is not None
            and expected != self.qdrant.vector_size
            and not self.qdrant.allow_named_vector_writes
            and not self.qdrant.write_vector_name
            and not (
                "qwen" in self.ml.encoder_name.lower() and self.qdrant.vector_size in {768, 2048}
            )
        ):
            raise ValueError(
                f"ML_ENCODER_NAME={self.ml.encoder_name} emits {expected} dimensions "
                f"but QDRANT_VECTOR_SIZE={self.qdrant.vector_size}. "
                "Update the vector size and re-index the collection."
            )
        if (
            self.app.env in {"staging", "production"}
            and self.auth.secret_key.get_secret_value() == _INSECURE_DEFAULT_AUTH_SECRET
        ):
            raise ValueError(
                "AUTH_SECRET_KEY must be explicitly configured in staging and production"
            )
        return self


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
    "AuthSettings",
    "CelerySettings",
    "DatabaseSettings",
    "DatasetSettings",
    "LLMSettings",
    "MLSettings",
    "MinIOSettings",
    "QdrantSettings",
    "RedisSettings",
    "SearchSettings",
    "Settings",
    "VideoSettings",
    "get_settings",
    "project_root",
]
