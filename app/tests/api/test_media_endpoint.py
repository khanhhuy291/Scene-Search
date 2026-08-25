"""Media delivery, and specifically byte ranges.

Range support is the difference between a working player and one that appears
broken: a ``<video>`` element seeks by asking for a byte range, so without it the
browser downloads a whole 20 MB clip before showing a frame and cannot jump to the
matched second at all. That makes these assertions product behaviour rather than
protocol trivia.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from api.deps import get_current_user
from api.main import app
from api.v1.media import _bucket_for_key, _parse_range, reset_media_client
from search.catalog import Keyframe, get_catalog, reset_catalog

POINT_ID = "11111111-2222-3333-4444-555555555555"
CLIP_BYTES = b"".join(bytes([index % 256]) for index in range(4096))


class FakeStat:
    def __init__(self, size: int) -> None:
        self.size = size


class FakeObject:
    """Stands in for the object-store read, which is a file-like sync stream."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self._position = 0
        self.closed = False
        self.released = False

    def read(self, amount: int | None = None) -> bytes:
        if amount is None:
            chunk = self._payload[self._position :]
        else:
            chunk = self._payload[self._position : self._position + amount]
        self._position += len(chunk)
        return chunk

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


class FakeMinio:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.reads: list[tuple[int, int]] = []
        self.handed_out: list[FakeObject] = []

    def stat_object(self, bucket: str, key: str) -> FakeStat:
        return FakeStat(len(self.payload))

    def get_object(self, bucket: str, key: str, offset: int = 0, length: int = 0) -> FakeObject:
        self.reads.append((offset, length))
        window = self.payload[offset : offset + length] if length else self.payload[offset:]
        handle = FakeObject(window)
        self.handed_out.append(handle)
        return handle


@pytest.fixture(autouse=True)
def _signed_in_media_client() -> None:
    """Media routes require a session; these tests are about Range delivery."""

    app.dependency_overrides[get_current_user] = lambda: MagicMock()
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def indexed_clip(monkeypatch: pytest.MonkeyPatch) -> FakeMinio:
    """A catalog holding one keyframe, and a fake store behind it."""

    reset_catalog()
    reset_media_client()
    catalog = get_catalog()
    keyframe = Keyframe(
        point_id=POINT_ID,
        video_id="video-a",
        timestamp_s=18.9,
        frame_no=568,
        caption="A rainy street.",
        thumbnail_key="thumbnails/a.jpg",
        video_key="videos/a.mov",
    )
    monkeypatch.setattr(catalog, "_by_id", {POINT_ID: keyframe})

    async def _skip_reload(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(catalog, "ensure_loaded", _skip_reload)
    store = FakeMinio(CLIP_BYTES)
    monkeypatch.setattr("api.v1.media._client", lambda: store)
    yield store
    reset_catalog()
    reset_media_client()


# -- range parsing -----------------------------------------------------------


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("bytes=0-99", (0, 99)),
        ("bytes=100-", (100, 4095)),
        # A suffix range: the last 500 bytes, which is how a player finds an MP4
        # moov atom when it was written at the end of the file.
        ("bytes=-500", (3596, 4095)),
        # Clamped to the object rather than rejected.
        ("bytes=0-999999", (0, 4095)),
        # Ignored, meaning "send everything": the spec says to ignore a malformed
        # Range, and 416 here would break a client over a header it can recover
        # from.
        ("bytes=abc-def", None),
        ("items=0-99", None),
        ("", None),
    ],
)
def test_range_header_is_resolved_to_offsets(header: str, expected: tuple[int, int] | None) -> None:
    assert _parse_range(header, 4096) == expected


# -- clip delivery -----------------------------------------------------------


@pytest.mark.asyncio
async def test_a_full_request_advertises_range_support(client, indexed_clip) -> None:
    """Without ``Accept-Ranges`` the player will not offer seeking at all."""

    response = await client.get(f"/api/v1/media/clip/{POINT_ID}")

    assert response.status_code == 200
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-length"] == str(len(CLIP_BYTES))
    assert response.content == CLIP_BYTES


@pytest.mark.asyncio
async def test_a_ranged_request_returns_only_that_range(client, indexed_clip) -> None:
    response = await client.get(
        f"/api/v1/media/clip/{POINT_ID}", headers={"Range": "bytes=1000-1099"}
    )

    assert response.status_code == 206
    assert response.headers["content-range"] == f"bytes 1000-1099/{len(CLIP_BYTES)}"
    assert response.headers["content-length"] == "100"
    assert response.content == CLIP_BYTES[1000:1100]
    # Only the requested window was read from the store, which is the point: the
    # alternative streams 20 MB to answer a seek.
    assert indexed_clip.reads == [(1000, 100)]


@pytest.mark.asyncio
async def test_a_range_past_the_end_is_rejected_with_the_real_size(client, indexed_clip) -> None:
    response = await client.get(f"/api/v1/media/clip/{POINT_ID}", headers={"Range": "bytes=99999-"})

    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{len(CLIP_BYTES)}"


@pytest.mark.asyncio
async def test_the_store_connection_is_released_after_streaming(client, indexed_clip) -> None:
    """A leaked connection per seek exhausts the pool within a few videos."""

    await client.get(f"/api/v1/media/clip/{POINT_ID}", headers={"Range": "bytes=0-99"})

    assert indexed_clip.handed_out
    assert all(handle.closed and handle.released for handle in indexed_clip.handed_out)


@pytest.mark.asyncio
async def test_an_unknown_point_is_not_a_path_into_the_bucket(client, indexed_clip) -> None:
    # The route resolves keys from the index precisely so a caller cannot name an
    # object; an unknown id must therefore 404 rather than reach the store.
    response = await client.get("/api/v1/media/clip/not-a-real-point")

    assert response.status_code == 404
    assert indexed_clip.reads == []


def test_shared_store_routes_frames_and_videos_to_separate_buckets(monkeypatch) -> None:
    from types import SimpleNamespace

    from api.v1 import media as media_module

    monkeypatch.setattr(
        media_module,
        "get_settings",
        lambda: SimpleNamespace(
            minio=SimpleNamespace(
                scene_media_endpoint="minio.viettech.fit",
                scene_media_bucket="scenesearch",
                raw_bucket="scenesearch-raw",
                derived_bucket="scenesearch-derived",
            )
        ),
    )

    assert _bucket_for_key("videos/a.mov") == "scenesearch-derived"
    assert _bucket_for_key("frames/a/frame_00008.jpg") == "scenesearch-derived"
    assert _bucket_for_key("thumbnails/a.jpg") == "scenesearch-derived"


def test_local_media_is_only_read_from_the_derived_bucket(monkeypatch) -> None:
    from types import SimpleNamespace

    from api.v1 import media as media_module

    monkeypatch.setattr(
        media_module,
        "get_settings",
        lambda: SimpleNamespace(
            minio=SimpleNamespace(
                scene_media_endpoint=None,
                scene_media_bucket="scenesearch",
                raw_bucket="scenesearch-raw",
                derived_bucket="scenesearch-derived",
            )
        ),
    )

    assert _bucket_for_key("thumbnails/a.jpg") == "scenesearch-derived"
    assert _bucket_for_key("videos/a.mp4") == "scenesearch-derived"
