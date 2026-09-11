from __future__ import annotations

import math
from uuid import UUID

import pytest
from PIL import Image

from pipelines.common.errors import EmbeddingError
from pipelines.common.types import FrameRecord
from pipelines.ingestion.deduplicator import DedupStats, filter_near_duplicates
from pipelines.ingestion.embedder import embed_frames, embed_frames_qwen, embed_scenes
from pipelines.ingestion.indexer import build_scene_points
from pipelines.ingestion.privacy_verifier import verified_frames
from pipelines.ingestion.sampler import UniformFrameSampler
from pipelines.ingestion.scene_builder import build_scenes, scene_id

VIDEO_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def frame(timestamp_ms: int, index: int, *, privacy: str = "verified") -> FrameRecord:
    return FrameRecord(
        timestamp_ms=timestamp_ms,
        frame_index=index,
        image=Image.new("RGB", (8, 8)),
        privacy_status=privacy,
    )


def close_frames(frames):
    for item in frames:
        item.image.close()


def test_sampler_uses_configured_rate_and_max_gap() -> None:
    source = [frame(ms, i) for i, ms in enumerate((0, 100, 500, 1000, 3000))]
    sampled = list(UniformFrameSampler(1, max_gap_sec=1.5).sample(source))
    try:
        assert [item.timestamp_ms for item in sampled] == [0, 1000, 3000]
    finally:
        close_frames(sampled)


def test_scene_builder_groups_frames_and_has_deterministic_ids() -> None:
    source = [frame(0, 0), frame(1000, 1), frame(2000, 2), frame(8000, 3)]
    scenes = build_scenes(
        source,
        video_id=VIDEO_ID,
        pipeline_version="v1",
        max_duration_sec=5,
        gap_threshold_sec=2,
    )
    try:
        assert [len(scene.keyframes) for scene in scenes] == [3, 1]
        assert scenes[0].scene_id == scene_id(VIDEO_ID, "v1", 0)
        assert scenes[0].scene_id == scene_id(VIDEO_ID, "v1", 0)
    finally:
        close_frames(source)


def test_privacy_verifier_never_publishes_failed_frame() -> None:
    safe = frame(0, 0)
    failed = frame(1000, 1, privacy="failed")
    output = list(verified_frames([safe, failed]))
    try:
        assert output == [safe]
    finally:
        safe.image.close()


class StubEncoder:
    dimension = 4
    model_version = "stub-v1"

    def encode_images(self, images):
        return [[0.5] * 4 for _ in images]

    def encode_texts(self, texts):
        return [[0.5] * 4 for _ in texts]


def test_embedded_duplicate_frames_are_removed_and_coverage_is_preserved() -> None:
    source = [frame(0, 0), frame(1000, 1), frame(2000, 2)]
    embedded = embed_frames(source, encoder=StubEncoder(), batch_size=2)
    stats = DedupStats()
    retained = list(filter_near_duplicates(embedded, enabled=True, threshold=0.99, stats=stats))
    try:
        assert retained == [source[0]]
        assert retained[0].covers_end_ms == 2000
        assert stats.seen == 3
        assert stats.dropped == 2
    finally:
        close_frames(retained)


def test_embedding_dimension_validation() -> None:
    source = [frame(0, 0)]
    scenes = build_scenes(source, video_id=VIDEO_ID, pipeline_version="v1")
    try:
        with pytest.raises(EmbeddingError, match="does not match"):
            embed_scenes(
                scenes,
                encoder=StubEncoder(),
                expected_dimension=8,
                model="stub",
                version="stub-v1",
                batch_size=2,
            )
    finally:
        close_frames(source)


def test_scene_point_id_is_deterministic_and_payload_is_searchable() -> None:
    source = [frame(0, 0), frame(1000, 1)]
    scenes = build_scenes(source, video_id=VIDEO_ID, pipeline_version="v1")
    scenes[0].thumbnail_key = f"thumbnails/{VIDEO_ID}/preview.jpg"
    scenes[0].preview_key = f"videos/{VIDEO_ID}/preview.mp4"
    vectors = embed_scenes(
        scenes,
        encoder=StubEncoder(),
        expected_dimension=4,
        model="stub",
        version="stub-v1",
        batch_size=2,
    )
    try:
        first = build_scene_points(scenes, vectors, dataset="test")[0]
        second = build_scene_points(scenes, vectors, dataset="test")[0]
        assert first.id == second.id
        UUID(str(first.id))
        assert first.payload["scene_id"] == scenes[0].scene_id
        assert first.payload["privacy_status"] == "verified"
        assert first.payload["thumbnail_key"] == scenes[0].thumbnail_key
        assert first.payload["video_key"] == scenes[0].preview_key
        assert math.isclose(sum(value * value for value in first.vector), 1.0)
    finally:
        close_frames(source)


def test_siglip_dedup_and_hybrid_qwen_siglip_scene_points() -> None:
    class MockSiglipEncoder:
        dimension = 768
        model_version = "siglip-v1"

        def encode_images(self, images):
            return [[0.0] * 768 for _ in images]

    class MockQwenEncoder:
        dimension = 2048
        model_version = "qwen-v1"

        def encode_images(self, images):
            return [[0.0] * 2048 for _ in images]

    # Create 3 frames where first two are near-duplicates
    f0 = frame(0, 0)
    f1 = frame(100, 1)
    f2 = frame(2000, 2)
    source = [f0, f1, f2]

    # Assign SigLIP vectors for dedup
    f0.embedding = [1.0] + [0.0] * 767
    f1.embedding = [1.0] + [0.0] * 767  # duplicate of f0
    f2.embedding = [0.0, 1.0] + [0.0] * 766

    retained = list(filter_near_duplicates(source, enabled=True, threshold=0.98))
    assert len(retained) == 2
    assert retained[0].timestamp_ms == 0
    assert retained[1].timestamp_ms == 2000

    embed_frames_qwen(retained, encoder=MockQwenEncoder(), batch_size=2)
    assert retained[0].qwen_embedding is not None
    assert len(retained[0].qwen_embedding) == 2048

    scenes = build_scenes(retained, video_id=VIDEO_ID, pipeline_version="v1")
    embeddings = embed_scenes(
        scenes,
        qwen_encoder=MockQwenEncoder(),
        siglip_encoder=MockSiglipEncoder(),
        expected_dimension=2048,
    )
    assert len(embeddings) == 1
    assert isinstance(embeddings[0].vector, dict)
    assert "qwen" in embeddings[0].vector
    assert "siglip" in embeddings[0].vector
    assert len(embeddings[0].vector["qwen"]) == 2048
    assert len(embeddings[0].vector["siglip"]) == 768

    points = build_scene_points(scenes, embeddings, dataset="test")
    assert len(points) == 1
    assert isinstance(points[0].vector, dict)
    assert points[0].vector["qwen"] == embeddings[0].vector["qwen"]
    assert points[0].vector["siglip"] == embeddings[0].vector["siglip"]
    assert points[0].payload["scene_id"] == scenes[0].scene_id
    assert points[0].payload["dataset"] == "test"
