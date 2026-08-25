"""Startup must provision every bucket, not only the default one.

The raw/derived split is the privacy mechanism (ADR-0003). If startup provisions
only the default bucket, ingestion reaches a state where it holds an original and
has nowhere separate to put it -- and the failure appears at write time, deep in a
Celery task, rather than at boot.
"""

from __future__ import annotations

from typing import Any

import pytest

from infrastructure import minio as minio_module


@pytest.fixture(autouse=True)
def _reset() -> Any:
    minio_module.get_settings.cache_clear()
    minio_module.reset_storage_cache()
    yield
    minio_module.get_settings.cache_clear()
    minio_module.reset_storage_cache()


async def test_startup_ensures_all_three_buckets(monkeypatch: pytest.MonkeyPatch) -> None:
    ensured: list[str] = []

    class FakeMinio:
        def __init__(self, **_: Any) -> None:
            pass

        def bucket_exists(self, bucket: str) -> bool:
            return False

        def make_bucket(self, bucket: str, location: Any = None) -> None:
            ensured.append(bucket)

    monkeypatch.setattr(minio_module, "Minio", FakeMinio)

    from api import main as api_main

    async def run_inline(function: Any) -> Any:
        # This unit test verifies bucket selection, not asyncio's thread pool.
        # Running inline also keeps it deterministic in thread-limited CI jobs.
        return function()

    monkeypatch.setattr(api_main.asyncio, "to_thread", run_inline)

    await api_main._check_minio()

    settings = minio_module.get_settings().minio
    assert set(ensured) == {
        settings.bucket,
        settings.raw_bucket,
        settings.derived_bucket,
    }, ensured


def test_raw_bucket_is_not_servable_after_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(minio_module, "Minio", lambda **_: object())
    assert minio_module.get_raw_storage().servable is False
    assert minio_module.get_derived_storage().servable is True
