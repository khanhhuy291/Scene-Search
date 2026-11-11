"""The single coordinator for the production ingestion stage order."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from loguru import logger

from core.config import Settings, get_settings
from infrastructure.minio import MinIOStorage, get_derived_storage, get_raw_storage
from ml.anonymize import BlurRegionDetector, LabelHeuristicDetector
from ml.encoder import Encoder, get_qwen_encoder, get_siglip_encoder
from pipelines.common.context import PipelineContext
from pipelines.common.errors import (
    PipelineError,
    RetryablePersistenceError,
    VideoAcquireError,
)
from pipelines.ingestion.anonymizer import anonymize_frames
from pipelines.ingestion.behavior_detector import NoopBehaviorDetector, TemporalBehaviorDetector
from pipelines.ingestion.deduplicator import DedupStats, filter_near_duplicates
from pipelines.ingestion.embedder import embed_frames, embed_frames_qwen, embed_scenes
from pipelines.ingestion.indexer import build_scene_points, persist_vectors
from pipelines.ingestion.metadata_extractor import extract_metadata, extract_scene_vlm_metadata
from pipelines.ingestion.preview_generator import generate_previews
from pipelines.ingestion.privacy_verifier import verified_frames
from pipelines.ingestion.sampler import sample_frames
from pipelines.ingestion.scene_builder import build_scenes
from pipelines.ingestion.tracker import ObjectTracker, PassthroughTracker
from pipelines.ingestion.video_reader import acquire_video, decode_video, validate_video
from repositories import corpus
from search.index import delete_by_video, reindex_video


class DefaultPipelineRepository:
    get_video_for_pipeline = staticmethod(corpus.get_video_for_pipeline)
    insert_segments = staticmethod(corpus.insert_segments)
    delete_segments = staticmethod(corpus.delete_segments)
    mark_video_indexed = staticmethod(corpus.mark_video_indexed)


class DefaultPipelineIndexer:
    reindex_video = staticmethod(reindex_video)
    delete_by_video = staticmethod(delete_by_video)


@dataclass
class PipelineDependencies:
    repository: Any
    scene_indexer: Any
    raw_storage: MinIOStorage
    derived_storage: MinIOStorage
    encoder: Encoder
    privacy_detector: BlurRegionDetector
    tracker: ObjectTracker
    behavior_detector: TemporalBehaviorDetector
    settings: Settings
    siglip_encoder: Encoder | None = None


def default_dependencies() -> PipelineDependencies:
    return PipelineDependencies(
        repository=DefaultPipelineRepository(),
        scene_indexer=DefaultPipelineIndexer(),
        raw_storage=get_raw_storage(),
        derived_storage=get_derived_storage(),
        encoder=get_qwen_encoder(),
        siglip_encoder=get_siglip_encoder(),
        privacy_detector=LabelHeuristicDetector(),
        tracker=PassthroughTracker(),
        behavior_detector=NoopBehaviorDetector(),
        settings=get_settings(),
    )


async def _stage(progress: Any, value: int, name: str) -> None:
    if progress is not None:
        await progress(value, name)


async def run_ingestion_pipeline(
    *,
    job_id: str,
    video_id: str,
    pipeline_version: str = "scene-ingestion-v1",
    progress: Any = None,
    dependencies: PipelineDependencies | None = None,
) -> dict[str, Any]:
    """Acquire a registered MinIO video and produce persisted, searchable scenes."""
    deps = dependencies or default_dependencies()
    started = time.perf_counter()
    video_uuid = UUID(video_id)
    video = await deps.repository.get_video_for_pipeline(video_uuid)
    if video is None:
        raise VideoAcquireError(f"Video {video_id} does not exist", stage="acquire")
    if not video.raw_object_key:
        raise VideoAcquireError(f"Video {video_id} has no raw object", stage="acquire")
    if video.ingested_at is not None and video.model_version == deps.encoder.model_version:
        return {"video_id": video_id, "duplicate": True, "scenes_indexed": 0}

    ctx = PipelineContext(
        job_id=job_id,
        video_id=video_id,
        raw_minio_key=video.raw_object_key,
        pipeline_version=pipeline_version,
        embedding_model=deps.settings.ml.encoder_name,
        settings=deps.settings,
    )
    uploaded: list[str] = []
    owned_frames: list[Any] = []
    persistence_started = False
    try:
        with ctx:
            await _stage(progress, 5, "acquire")
            stage_started = time.perf_counter()
            local_video = await acquire_video(ctx, deps.raw_storage)
            validate_video(
                local_video,
                max_duration_s=deps.settings.video.max_duration_s,
                max_pixels=deps.settings.video.max_pixels,
            )
            ctx.metrics["acquire_duration_ms"] = round(
                (time.perf_counter() - stage_started) * 1000, 2
            )

            await _stage(progress, 15, "decode_sample_privacy")

            def own_frames(frames: Any) -> Any:
                for frame in frames:
                    owned_frames.append(frame)
                    yield frame

            decoded = own_frames(decode_video(local_video))
            sampled = sample_frames(
                decoded,
                fps=deps.settings.video.sample_fps,
                max_gap_sec=deps.settings.video.sampling_max_gap_sec,
            )
            safe = verified_frames(anonymize_frames(sampled, deps.privacy_detector))
            enriched = extract_metadata(safe)
            tracked = deps.tracker.track(enriched)
            behavior_frames = deps.behavior_detector.detect(tracked)

            await _stage(progress, 35, "siglip_embedding_dedup")
            siglip_enc = deps.siglip_encoder or deps.encoder
            embedded_frames = embed_frames(
                behavior_frames,
                encoder=siglip_enc,
                batch_size=deps.settings.ml.batch_size,
            )
            dedup = DedupStats()
            retained_frames = list(
                filter_near_duplicates(
                    embedded_frames,
                    enabled=deps.settings.video.dedup_enabled,
                    threshold=deps.settings.video.dedup_threshold,
                    stats=dedup,
                )
            )

            await _stage(progress, 50, "qwen_embedding_retained")
            embed_frames_qwen(
                retained_frames,
                encoder=deps.encoder,
                batch_size=deps.settings.ml.batch_size,
            )

            await _stage(progress, 60, "scene_building")
            scenes = build_scenes(
                retained_frames,
                video_id=video_id,
                pipeline_version=pipeline_version,
                max_duration_sec=deps.settings.video.segment_seconds,
                gap_threshold_sec=deps.settings.video.segment_gap_tolerance_s,
                sample_interval_ms=max(1, round(1000 / deps.settings.video.sample_fps)),
            )
            if not scenes:
                raise PipelineError("Pipeline produced no privacy-safe scenes", stage="privacy")
            ctx.metrics["sampled_frames"] = sum(len(scene.keyframes) for scene in scenes)
            ctx.metrics["dedup_seen"] = dedup.seen
            ctx.metrics["dedup_dropped"] = dedup.dropped
            ctx.metrics["dedup_drop_ratio"] = round(dedup.drop_ratio, 6)
            ctx.metrics["scenes_created"] = len(scenes)

            await _stage(progress, 65, "vlm_metadata_extraction")
            await extract_scene_vlm_metadata(scenes)

            await _stage(progress, 70, "embedding")
            embeddings = embed_scenes(
                scenes,
                encoder=deps.encoder,
                qwen_encoder=deps.encoder if deps.siglip_encoder is not None else None,
                siglip_encoder=deps.siglip_encoder,
                expected_dimension=deps.settings.qdrant.vector_size,
                model=deps.settings.ml.encoder_name,
                version=deps.encoder.model_version,
                batch_size=deps.settings.ml.batch_size,
            )
            ctx.metrics["embedding_batches"] = sum(
                (len(scene.keyframes) + deps.settings.ml.batch_size - 1)
                // deps.settings.ml.batch_size
                for scene in scenes
            )

            await _stage(progress, 80, "preview_generation")
            uploaded = await generate_previews(ctx, scenes, deps.derived_storage, local_video)

            await _stage(progress, 85, "persistence")
            rows = [
                corpus.SegmentRow(
                    id=UUID(scene.scene_id),
                    segment_index=index,
                    ts_start_s=scene.start_ms / 1000,
                    ts_end_s=scene.end_ms / 1000,
                    frame_count=len(scene.keyframes),
                    preview_object_key=scene.preview_key,
                    privacy_status=scene.privacy_status,
                    pipeline_version=pipeline_version,
                    embedding_model=deps.settings.ml.encoder_name,
                    model_version=deps.encoder.model_version,
                )
                for index, scene in enumerate(scenes)
            ]
            try:
                persistence_started = True
                await deps.repository.delete_segments(video_uuid)
                await deps.scene_indexer.delete_by_video(video_id)
                await deps.repository.insert_segments(video_uuid, rows)
                points = build_scene_points(scenes, embeddings, dataset=video.dataset)
                written = await persist_vectors(video_id, points, deps.scene_indexer)
                indexed = await deps.repository.mark_video_indexed(
                    video_uuid, model_version=deps.encoder.model_version
                )
                if indexed is False:
                    raise PipelineError(
                        "Video ingestion was cancelled during persistence",
                        stage="persistence",
                    )
            except Exception as exc:
                if isinstance(exc, PipelineError):
                    raise
                raise RetryablePersistenceError(
                    "Unable to persist scene metadata", stage="persistence"
                ) from exc

            ctx.metrics["qdrant_points_upserted"] = written
            ctx.metrics["pipeline_total_duration_ms"] = round(
                (time.perf_counter() - started) * 1000, 2
            )
            logger.bind(job_id=job_id, video_id=video_id, stage="finalize").info(
                "Ingestion pipeline completed: {metrics}", metrics=ctx.metrics
            )
            await _stage(progress, 100, "completed")
            return {
                "video_id": video_id,
                "job_id": job_id,
                "duplicate": False,
                "scenes_indexed": len(scenes),
                "vectors_indexed": written,
                "previews_created": len(
                    {scene.preview_key for scene in scenes if scene.preview_key}
                ),
                "metrics": dict(ctx.metrics),
                "pipeline_version": pipeline_version,
            }
    except Exception as exc:
        stage = exc.stage if isinstance(exc, PipelineError) else "unknown"
        logger.bind(job_id=job_id, video_id=video_id, stage=stage).exception(
            "Ingestion pipeline failed: {error_type}", error_type=type(exc).__name__
        )
        # Retry safety: raw input remains registered, while every derived side
        # effect from this attempt is removed on a best-effort basis.
        if persistence_started:
            cleanup = [
                ("Qdrant points", deps.scene_indexer.delete_by_video(video_id)),
                ("PostgreSQL segments", deps.repository.delete_segments(video_uuid)),
            ]
            for label, operation in cleanup:
                try:
                    await operation
                except Exception:
                    logger.exception("Failed to clean up {label}", label=label)
        for key in uploaded:
            try:
                await asyncio.to_thread(deps.derived_storage.delete_object, key)
            except Exception:
                logger.exception("Failed to clean up preview {key}", key=key)
        raise
    finally:
        # Ownership begins immediately after decode so failures before scene
        # construction cannot strand native image buffers in a long-lived worker.
        for frame in owned_frames:
            try:
                frame.image.close()
            except Exception:
                logger.exception("Failed to close decoded frame {index}", index=frame.frame_index)


__all__ = ["PipelineDependencies", "default_dependencies", "run_ingestion_pipeline"]
