"""Deterministic identity of source, models, preprocessing and representation settings."""

import hashlib
import json

from core.config import Settings
from core.ingestion import SEQUENCE_METADATA_PROMPT_VERSION
from core.privacy import PLAYBACK_VERSION, THUMBNAIL_VERSION
from pipelines.ingestion.metadata_extractor import VLM_METADATA_PROMPT


def ingestion_snapshot(
    settings: Settings,
    *,
    qwen_version: str,
    siglip_version: str,
) -> dict:
    ml_fields = {
        "encoder_name",
        "encoder_pretrained",
        "model_version",
        "qwen_embedding_url",
        "qwen_model_name",
        "dtype",
        "image_size",
        "privacy_yolo_weights",
        "privacy_yolo_weights_sha256",
        "privacy_yolo_weights_url",
        "privacy_yolo_confidence",
        "privacy_yolo_image_size",
    }
    identity = {
        "qwen_version": qwen_version,
        "siglip_version": siglip_version,
        "models": settings.ml.model_dump(mode="json", include=ml_fields),
        "video": settings.video.model_dump(mode="json"),
        "pooling": {"siglip": "all_sampled_mean_l2", "qwen": "selected_mean_l2"},
        "vlm": {
            "enabled": bool(settings.llm.api_key and settings.llm.api_key.get_secret_value()),
            "model": settings.llm.model,
            "provider": str(settings.llm.base_url),
        },
        "prompt_version": SEQUENCE_METADATA_PROMPT_VERSION,
        "prompt_sha256": hashlib.sha256(VLM_METADATA_PROMPT.encode()).hexdigest(),
        "media": {
            "playback_version": PLAYBACK_VERSION,
            "thumbnail_version": THUMBNAIL_VERSION,
            "thumbnail_max_edge": settings.dataset.thumbnail_max_edge,
            "thumbnail_quality": settings.dataset.thumbnail_quality,
        },
    }
    return identity


def ingestion_fingerprint(
    checksum: str,
    settings: Settings,
    *,
    qwen_version: str,
    siglip_version: str,
) -> str:
    if not checksum:
        raise ValueError("Ingestion identity requires a source checksum")
    return snapshot_fingerprint(
        ingestion_snapshot(
            settings,
            qwen_version=qwen_version,
            siglip_version=siglip_version,
        )
    )


def snapshot_fingerprint(snapshot: dict) -> str:
    return hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
