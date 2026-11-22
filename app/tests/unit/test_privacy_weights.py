from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from hashlib import sha256
from threading import Barrier

import httpx
import pytest

from core.config import MLSettings
from ml import privacy_weights

CHECKPOINT = b"test checkpoint"
DIGEST = sha256(CHECKPOINT).hexdigest()
URL = "https://example.test/releases/v1/privacy.pt"


@pytest.fixture(autouse=True)
def clear_cached_resolution():
    privacy_weights._resolve_download.cache_clear()
    yield
    privacy_weights._resolve_download.cache_clear()


@pytest.fixture
def remote_settings(tmp_path):
    return MLSettings(
        privacy_yolo_weights=None,
        privacy_yolo_weights_url=URL,
        privacy_yolo_weights_sha256=DIGEST,
        privacy_yolo_cache_dir=tmp_path,
    )


@pytest.fixture
def downloads(monkeypatch):
    calls = []

    @contextmanager
    def stream(method, url, **kwargs):
        calls.append((method, url))
        yield httpx.Response(200, content=CHECKPOINT, request=httpx.Request(method, url))

    monkeypatch.setattr(privacy_weights.httpx, "stream", stream)
    return calls


def test_download_revalidated_and_reused_offline(remote_settings, downloads):
    target = privacy_weights.resolve_privacy_weights(remote_settings)
    assert target.read_bytes() == CHECKPOINT
    assert target.name == f"privacy-{DIGEST}.pt"
    privacy_weights._resolve_download.cache_clear()
    assert privacy_weights.resolve_privacy_weights(remote_settings) == target
    assert downloads == [("GET", URL)]


def test_parallel_workers_share_one_download(remote_settings, downloads):
    ready = Barrier(2)

    def start():
        ready.wait(timeout=5)
        return privacy_weights.resolve_privacy_weights(remote_settings)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = executor.submit(start), executor.submit(start)
        assert first.result(timeout=10) == second.result(timeout=10)
    assert downloads == [("GET", URL)]


def test_checksum_mismatch_leaves_no_checkpoint(remote_settings, downloads):
    settings = remote_settings.model_copy(update={"privacy_yolo_weights_sha256": "0" * 64})
    with pytest.raises(ValueError, match="SHA-256"):
        privacy_weights.resolve_privacy_weights(settings)
    assert downloads == [("GET", URL)]
    assert list(settings.privacy_yolo_cache_dir.glob("*.pt")) == []
    assert list(settings.privacy_yolo_cache_dir.glob("*.part")) == []


def test_corrupt_cache_is_replaced(remote_settings, downloads):
    target = remote_settings.privacy_yolo_cache_dir / f"privacy-{DIGEST}.pt"
    target.write_bytes(b"corrupt")
    assert privacy_weights.resolve_privacy_weights(remote_settings) == target
    assert target.read_bytes() == CHECKPOINT
    assert downloads == [("GET", URL)]


def test_local_checkpoint_takes_precedence(tmp_path, remote_settings, downloads):
    weights = tmp_path / "local.pt"
    weights.touch()
    settings = remote_settings.model_copy(update={"privacy_yolo_weights": weights})
    assert privacy_weights.resolve_privacy_weights(settings) == weights
    assert not downloads


def test_failed_download_removes_partial_file(remote_settings, monkeypatch):
    @contextmanager
    def stream(*args, **kwargs):
        raise httpx.ConnectError("offline")
        yield

    monkeypatch.setattr(privacy_weights.httpx, "stream", stream)
    with pytest.raises(httpx.ConnectError, match="offline"):
        privacy_weights.resolve_privacy_weights(remote_settings)
    assert list(remote_settings.privacy_yolo_cache_dir.glob("*.part")) == []
