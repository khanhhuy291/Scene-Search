"""Settings for the ML encoder and its agreement with the Qdrant collection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.config import DatasetSettings, MLSettings, QdrantSettings, Settings


def test_vector_size_is_no_longer_pinned_to_one_encoder() -> None:
    # ADR-0001: swapping encoders must be a re-index, not a schema migration.
    assert QdrantSettings(vector_size=1152).vector_size == 1152


@pytest.mark.parametrize("size", [32, 8192])
def test_vector_size_rejects_implausible_dimensions(size: int) -> None:
    with pytest.raises(ValidationError):
        QdrantSettings(vector_size=size)


def test_defaults_are_self_consistent() -> None:
    settings = Settings()
    if "Qwen" in settings.ml.encoder_name:
        assert settings.qdrant.vector_size == 2048
    else:
        assert settings.qdrant.vector_size == 768


def test_mismatched_encoder_dimension_is_rejected_at_startup() -> None:
    # Catching this here is far cheaper than a Qdrant upsert rejection partway
    # through an index run.
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            ml=MLSettings(encoder_name="ViT-SO400M-14-SigLIP-384"),
            qdrant=QdrantSettings(vector_size=768),
        )
    assert "1152" in str(excinfo.value)


def test_matching_encoder_dimension_is_accepted() -> None:
    settings = Settings(
        ml=MLSettings(encoder_name="ViT-SO400M-14-SigLIP-384"),
        qdrant=QdrantSettings(vector_size=1152),
    )
    assert settings.qdrant.vector_size == 1152


def test_unknown_encoder_is_not_blocked() -> None:
    # An unrecognized name means the dimension cannot be checked, not that the
    # encoder is invalid. The benchmark script verifies it against the
    # configured size before any indexing happens.
    settings = Settings(
        ml=MLSettings(encoder_name="some-custom-encoder"),
        qdrant=QdrantSettings(vector_size=512),
    )
    assert settings.qdrant.vector_size == 512


def test_dataset_manifest_path_is_derived_from_root() -> None:
    settings = DatasetSettings(root="data/subset")
    assert settings.manifest_path.as_posix() == "data/subset/manifest.jsonl"


def test_dataset_defaults_match_adr_0005() -> None:
    settings = DatasetSettings()

    assert settings.name == "driving-video-object-tracking"
    assert settings.root == Path("data/driving-video-object-tracking")


def test_known_dimensions_match_open_clip_configs() -> None:
    """Pin the hardcoded dimension table to open_clip's own model configs.

    The table in ``Settings.encoder_dimension_must_match_collection`` is a
    hand-maintained copy of facts owned by open_clip. Verified once against
    open_clip 3.3.0; this test re-checks it whenever the ML extra is installed,
    so an upstream change cannot silently invalidate the startup guard.
    """

    open_clip = pytest.importorskip(
        "open_clip", reason="ML extra not installed; run 'make install-ml'"
    )
    from pathlib import Path

    configs = Path(open_clip.__file__).parent / "model_configs"
    expected = {
        "ViT-B-16-SigLIP": 768,
        "ViT-B-16-SigLIP-256": 768,
        "ViT-B-16-SigLIP-384": 768,
        "ViT-B-16-SigLIP-512": 768,
        "ViT-L-16-SigLIP-256": 1024,
        "ViT-L-16-SigLIP-384": 1024,
        "ViT-SO400M-14-SigLIP": 1152,
        "ViT-SO400M-14-SigLIP-384": 1152,
    }
    for name, dimension in expected.items():
        config = json.loads((configs / f"{name}.json").read_text())
        assert config["embed_dim"] == dimension, name


def test_default_encoder_image_size_matches_settings() -> None:
    open_clip = pytest.importorskip(
        "open_clip", reason="ML extra not installed; run 'make install-ml'"
    )
    from pathlib import Path

    settings = MLSettings(encoder_name="ViT-B-16-SigLIP")
    config = json.loads(
        (
            Path(open_clip.__file__).parent / "model_configs" / f"{settings.encoder_name}.json"
        ).read_text()
    )
    # A mismatch here means frames are preprocessed at the wrong resolution,
    # which degrades retrieval quietly rather than failing.
    assert config["vision_cfg"]["image_size"] == settings.image_size


def test_qwen_embedding_url_accepts_legacy_ml_prefixed_environment(monkeypatch) -> None:
    monkeypatch.delenv("QWEN_EMBEDDING_URL", raising=False)
    monkeypatch.setenv("ML_QWEN_EMBEDDING_URL", "http://qwen-embedding:8001/")

    assert MLSettings().qwen_embedding_url == "http://qwen-embedding:8001"


def test_qwen_embedding_url_rejects_markdown_link() -> None:
    with pytest.raises(ValidationError, match="plain URL"):
        MLSettings(
            qwen_embedding_url=(
                "[http://qwen-embedding:8001](http://qwen-embedding:8001)"
            )
        )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            '["http://localhost:3000","http://localhost:5173"]',
            ["http://localhost:3000", "http://localhost:5173"],
        ),
        (
            "[http://localhost:3000,http://localhost:5173]",
            ["http://localhost:3000", "http://localhost:5173"],
        ),
        (
            "http://localhost:3000,http://localhost:5173",
            ["http://localhost:3000", "http://localhost:5173"],
        ),
    ],
)
def test_cors_origins_accept_json_csv_and_unquoted_brackets(raw: str, expected: list[str]) -> None:
    from core.config import AppSettings

    assert AppSettings(cors_origins=raw).cors_origins == expected
