from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.v1 import media

POINT_ID = "11111111-2222-3333-4444-555555555555"
VERIFIED_THUMBNAIL = "videos/video-1/segments/scene-1/thumbnail-yolo-v1/job.jpg"


@pytest.fixture(autouse=True)
def media_store(monkeypatch):
    media.reset_media_client()
    store = MagicMock()
    store.read_object.return_value = b"thumbnail"
    monkeypatch.setattr(media, "get_derived_storage", lambda: store)
    yield store
    media.reset_media_client()


VIDEO_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
PLAYBACK_KEY = f"videos/{VIDEO_ID}/playback-yolo-v1/job.mp4"
PAYLOAD = b"anonymized playback"


@pytest.fixture
def indexed_playback(monkeypatch, media_store):
    video = SimpleNamespace(
        preview_blurred=True, preview_object_key=PLAYBACK_KEY, ingestion_status="indexed"
    )
    monkeypatch.setattr(media.corpus, "get_video_for_pipeline", AsyncMock(return_value=video))
    catalog = SimpleNamespace(get=lambda _: SimpleNamespace(video_id=VIDEO_ID))
    monkeypatch.setattr(media, "get_catalog", lambda: catalog)

    media_store.bucket = "derived"
    media_store.client.stat_object.return_value = SimpleNamespace(size=len(PAYLOAD))

    def get_object(bucket, key, *, offset, length):
        response = MagicMock()
        response.read.side_effect = BytesIO(PAYLOAD[offset : offset + length]).read
        responses.append(response)
        return response

    responses = []
    media_store.client.get_object.side_effect = get_object
    return video, responses


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [f"clip/{POINT_ID}", f"video/{VIDEO_ID}"])
async def test_source_playback_is_unavailable(client, media_store, indexed_playback, path):
    video, _ = indexed_playback
    video.preview_object_key = f"videos/{VIDEO_ID}/playback.mp4"
    response = await client.get(f"/api/v1/media/{path}", headers={"Range": "bytes=0-99"})
    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"
    media_store.client.stat_object.assert_not_called()


@pytest.mark.asyncio
async def test_unverified_playback_is_unavailable(client, media_store, indexed_playback):
    video, _ = indexed_playback
    video.preview_blurred = False
    response = await client.get(f"/api/v1/media/video/{VIDEO_ID}")
    assert response.status_code == 404
    media_store.client.stat_object.assert_not_called()


@pytest.mark.asyncio
async def test_verified_playback_is_streamed_with_range_support(
    client, media_store, indexed_playback
):
    _, responses = indexed_playback
    response = await client.get(f"/api/v1/media/clip/{POINT_ID}", headers={"Range": "bytes=3-6"})
    assert response.status_code == 206
    assert response.headers["content-range"] == f"bytes 3-6/{len(PAYLOAD)}"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-type"] == "video/mp4"
    assert response.content == PAYLOAD[3:7]
    media_store.client.get_object.assert_called_once_with(
        "derived", PLAYBACK_KEY, offset=3, length=4
    )
    responses[0].close.assert_called_once()
    responses[0].release_conn.assert_called_once()


@pytest.mark.asyncio
async def test_playback_rejects_unsatisfiable_range(client, media_store, indexed_playback):
    response = await client.get(f"/api/v1/media/video/{VIDEO_ID}", headers={"Range": "bytes=100-"})
    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{len(PAYLOAD)}"
    media_store.client.get_object.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("object_key", [VERIFIED_THUMBNAIL, "videos/video-1/thumbnail.jpg"])
async def test_thumbnail_requires_the_current_privacy_pipeline(
    client, monkeypatch, media_store, object_key
):
    catalog = SimpleNamespace(get=lambda _: SimpleNamespace(thumbnail_key=object_key))
    index = SimpleNamespace(
        retrieve=AsyncMock(return_value=[SimpleNamespace(payload={"thumbnail_key": object_key})])
    )
    monkeypatch.setattr(media, "get_catalog", lambda: catalog)
    monkeypatch.setattr(media, "get_qdrant_client", lambda: index)
    response = await client.get(f"/api/v1/media/thumbnail/{POINT_ID}")
    if object_key == VERIFIED_THUMBNAIL:
        assert response.status_code == 200
        assert response.content == b"thumbnail"
        media_store.read_object.assert_called_once_with(object_key)
    else:
        assert response.status_code == 404
        media_store.read_object.assert_not_called()
