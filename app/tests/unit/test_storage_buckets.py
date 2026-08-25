"""Two-bucket separation between restricted originals and servable derivatives.

The privacy guarantee in ADR-0003 rests on this: an original cannot be served
because the store holding it has no way to produce a URL, not because callers
remember to check.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from core.config import MinIOSettings
from infrastructure import minio as minio_module
from infrastructure.minio import MinIOStorage, RestrictedObjectError


@pytest.fixture(autouse=True)
def _reset() -> Any:
    minio_module.get_settings.cache_clear()
    minio_module.reset_storage_cache()
    yield
    minio_module.get_settings.cache_clear()
    minio_module.reset_storage_cache()


@pytest.fixture
def storages(monkeypatch: pytest.MonkeyPatch) -> tuple[MinIOStorage, MinIOStorage]:
    class FakeMinio:
        def __init__(self, **_: Any) -> None:
            self.signed: list[tuple[str, str]] = []
            self.deleted: list[tuple[str, str]] = []
            self.objects: list[str] = []

        def presigned_get_object(self, bucket: str, name: str, expires: Any = None) -> str:
            self.signed.append((bucket, name))
            return f"https://minio.local/{bucket}/{name}?sig=x"

        def remove_object(self, bucket: str, name: str) -> None:
            self.deleted.append((bucket, name))

        def list_objects(self, bucket: str, *, prefix: str, recursive: bool):
            assert recursive is True
            return [
                type("Object", (), {"object_name": name})
                for name in self.objects
                if name.startswith(prefix)
            ]

    monkeypatch.setattr(minio_module, "Minio", FakeMinio)
    settings = MinIOSettings()
    raw = MinIOStorage(settings, bucket=settings.raw_bucket, servable=False)
    derived = MinIOStorage(settings, bucket=settings.derived_bucket, servable=True)
    return raw, derived


def test_raw_and_derived_buckets_must_differ() -> None:
    # Sharing one bucket would make originals presignable, silently voiding the
    # entire guarantee.
    with pytest.raises(ValidationError, match="must differ"):
        MinIOSettings(raw_bucket="same", derived_bucket="same")


def test_restricted_store_refuses_to_sign(storages: tuple[MinIOStorage, MinIOStorage]) -> None:
    raw, _ = storages
    with pytest.raises(RestrictedObjectError, match="restricted originals"):
        raw.get_presigned_url("videos/original.mp4")
    # Nothing reached the client; the refusal is structural, not a filter.
    assert raw.client.signed == []


def test_restricted_store_refuses_even_a_derived_looking_key(
    storages: tuple[MinIOStorage, MinIOStorage],
) -> None:
    # The refusal is a property of the store, not a guess from the object name.
    raw, _ = storages
    with pytest.raises(RestrictedObjectError):
        raw.get_presigned_url("thumbnails/frame.jpg")


def test_derived_store_signs_normally(storages: tuple[MinIOStorage, MinIOStorage]) -> None:
    _, derived = storages
    url = derived.get_presigned_url("thumbnails/frame.jpg")
    assert "scenesearch-derived" in url
    assert derived.client.signed == [("scenesearch-derived", "thumbnails/frame.jpg")]


def test_derived_store_uses_the_configured_ttl(
    storages: tuple[MinIOStorage, MinIOStorage],
) -> None:
    _, derived = storages
    assert derived.settings.url_ttl_seconds == 3600
    derived.get_presigned_url("a.jpg")  # must not raise with the default TTL


def test_expiry_bounds_are_enforced(storages: tuple[MinIOStorage, MinIOStorage]) -> None:
    _, derived = storages
    with pytest.raises(ValueError, match="between one second and seven days"):
        derived.get_presigned_url("a.jpg", expires=timedelta(days=8))


def test_empty_object_name_is_rejected(storages: tuple[MinIOStorage, MinIOStorage]) -> None:
    _, derived = storages
    with pytest.raises(ValueError, match="cannot be empty"):
        derived.get_presigned_url("   ")


def test_cleanup_deletes_from_the_selected_bucket(
    storages: tuple[MinIOStorage, MinIOStorage],
) -> None:
    raw, derived = storages
    raw.delete_object("raw/video/source.mp4")
    derived.delete_object("derived/video/thumbs/000001.jpg")

    assert raw.client.deleted == [(raw.bucket, "raw/video/source.mp4")]
    assert derived.client.deleted == [(derived.bucket, "derived/video/thumbs/000001.jpg")]


def test_prefix_cleanup_removes_only_objects_owned_by_video(
    storages: tuple[MinIOStorage, MinIOStorage],
) -> None:
    _, derived = storages
    derived.client.objects = [
        "videos/video-1/scenes/a/preview.jpg",
        "videos/video-1/scenes/b/preview.jpg",
        "videos/video-2/scenes/a/preview.jpg",
    ]

    deleted = derived.delete_prefix("videos/video-1/")

    assert deleted == 2
    assert derived.client.deleted == [
        (derived.bucket, "videos/video-1/scenes/a/preview.jpg"),
        (derived.bucket, "videos/video-1/scenes/b/preview.jpg"),
    ]


def test_factories_return_correctly_configured_stores(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(minio_module, "Minio", lambda **_: object())
    raw = minio_module.get_raw_storage()
    derived = minio_module.get_derived_storage()

    assert raw.servable is False
    assert derived.servable is True
    assert raw.bucket != derived.bucket
    # Cached per process.
    assert minio_module.get_raw_storage() is raw
    assert minio_module.get_derived_storage() is derived
