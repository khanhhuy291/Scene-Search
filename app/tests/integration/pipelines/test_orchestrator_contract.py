from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from PIL import Image

from core.config import MLSettings, QdrantSettings, Settings, VideoSettings
from ml.anonymize import FullFrameDetector
from pipelines.common.errors import EmbeddingError
from pipelines.common.types import FrameRecord
from pipelines.ingestion import orchestrator, preview_generator
from pipelines.ingestion.behavior_detector import NoopBehaviorDetector
from pipelines.ingestion.orchestrator import PipelineDependencies, run_ingestion_pipeline
from pipelines.ingestion.tracker import PassthroughTracker

VIDEO_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


class StubEncoder:
    dimension = 64
    model_version = "stub-v1"

    def encode_images(self, images):
        return [[0.125] * 64 for _ in images]

    def encode_texts(self, texts):
        return [[0.125] * 64 for _ in texts]


class Repository:
    def __init__(self):
        self.rows = []
        self.marked = False

    async def get_video_for_pipeline(self, video_id):
        return SimpleNamespace(
            id=video_id,
            raw_object_key="raw/video.mp4",
            ingested_at=None,
            model_version=None,
            dataset="test",
        )

    async def delete_segments(self, video_id):
        pass

    async def insert_segments(self, video_id, rows):
        self.rows = list(rows)
        return [row.id for row in rows]

    async def mark_video_indexed(self, video_id, *, model_version):
        self.marked = True


class Storage:
    def __init__(self):
        self.uploaded = []

    def upload_file(self, key, path, *, content_type):
        assert Path(path).is_file()
        self.uploaded.append(key)


class Indexer:
    def __init__(self):
        self.points = []

    async def delete_by_video(self, video_id):
        pass

    async def reindex_video(self, video_id, points):
        self.points = list(points)
        return len(points)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_registered_video_becomes_scene_preview_and_vector(monkeypatch) -> None:
    repository = Repository()
    storage = Storage()
    indexer = Indexer()
    settings = Settings(
        ml=MLSettings(encoder_name="stub", model_version="stub-v1", batch_size=2),
        qdrant=QdrantSettings(vector_size=64),
        video=VideoSettings(sample_fps=1, segment_seconds=5),
    )
    deps = PipelineDependencies(
        repository=repository,
        scene_indexer=indexer,
        raw_storage=storage,
        derived_storage=storage,
        encoder=StubEncoder(),
        privacy_detector=FullFrameDetector(),
        tracker=PassthroughTracker(),
        behavior_detector=NoopBehaviorDetector(),
        settings=settings,
    )

    async def acquire(ctx, raw_storage):
        path = ctx.open_temp_dir() / "input.mp4"
        path.touch()
        return path

    def decode(_path):
        for index in range(3):
            yield FrameRecord(
                timestamp_ms=index * 1000,
                frame_index=index,
                image=Image.new("RGB", (16, 12), (index * 20, 30, 40)),
            )

    monkeypatch.setattr(orchestrator, "acquire_video", acquire)
    monkeypatch.setattr(orchestrator, "validate_video", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator, "decode_video", decode)

    async def run_inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(preview_generator.asyncio, "to_thread", run_inline)

    result = await run_ingestion_pipeline(
        job_id="11111111-1111-4111-8111-111111111111",
        video_id=VIDEO_ID,
        dependencies=deps,
    )

    assert result["scenes_indexed"] == 1
    assert result["vectors_indexed"] == 1
    assert result["previews_created"] == 1
    assert repository.marked
    assert repository.rows[0].id == UUID(repository.rows[0].id.hex)
    assert repository.rows[0].privacy_status == "verified"
    assert len(indexer.points) == 1
    assert storage.uploaded == [
        f"{VIDEO_ID}/frame_00000.jpg",
        f"{VIDEO_ID}.mp4",
    ]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_frames_are_closed_when_embedding_fails(monkeypatch) -> None:
    class FailingEncoder(StubEncoder):
        def encode_images(self, images):
            raise EmbeddingError("encoder failed", stage="embedding")

    frames = [
        FrameRecord(
            timestamp_ms=index * 1000,
            frame_index=index,
            image=Image.new("RGB", (16, 12)),
        )
        for index in range(3)
    ]
    settings = Settings(
        ml=MLSettings(encoder_name="stub", model_version="stub-v1", batch_size=2),
        qdrant=QdrantSettings(vector_size=64),
        video=VideoSettings(sample_fps=1, segment_seconds=5),
    )
    deps = PipelineDependencies(
        repository=Repository(),
        scene_indexer=Indexer(),
        raw_storage=Storage(),
        derived_storage=Storage(),
        encoder=FailingEncoder(),
        privacy_detector=FullFrameDetector(),
        tracker=PassthroughTracker(),
        behavior_detector=NoopBehaviorDetector(),
        settings=settings,
    )

    async def acquire(ctx, raw_storage):
        path = ctx.open_temp_dir() / "input.mp4"
        path.touch()
        return path

    monkeypatch.setattr(orchestrator, "acquire_video", acquire)
    monkeypatch.setattr(orchestrator, "validate_video", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator, "decode_video", lambda _path: iter(frames))

    with pytest.raises(EmbeddingError):
        await run_ingestion_pipeline(
            job_id="11111111-1111-4111-8111-111111111111",
            video_id=VIDEO_ID,
            dependencies=deps,
        )

    for item in frames:
        with pytest.raises(ValueError, match="closed"):
            item.image.getpixel((0, 0))
