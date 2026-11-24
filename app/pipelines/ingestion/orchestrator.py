"""The single coordinator for the production ingestion stage order."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from loguru import logger

from core.config import Settings, get_settings
from core.ingestion import PIPELINE_VERSION
from infrastructure.minio import MinIOStorage, get_derived_storage, get_raw_storage
from ml.anonymize import BlurRegionDetector
from ml.encoder import Encoder, get_qwen_encoder, get_siglip_encoder
from ml.privacy_weights import resolve_privacy_weights
from ml.yolo_privacy import get_yolo_privacy_detector
from pipelines.common.context import PipelineContext
from pipelines.common.errors import (
    PipelineError,
    RetryablePersistenceError,
    VideoAcquireError,
)
from pipelines.ingestion.anonymizer import anonymize_frames
from pipelines.ingestion.behavior_detector import NoopBehaviorDetector, TemporalBehaviorDetector
from pipelines.ingestion.deduplicator import DedupStats, filter_near_duplicates
from pipelines.ingestion.embedder import embed_frames_qwen, embed_scenes, iter_embedded_frames
from pipelines.ingestion.indexer import build_scene_points, persist_vectors
from pipelines.ingestion.keyframe_selector import select_representative
from pipelines.ingestion.metadata_extractor import extract_metadata, extract_scene_vlm_metadata
from pipelines.ingestion.preview_generator import generate_previews, stage_scene_thumbnail
from pipelines.ingestion.privacy_verifier import verified_frames
from pipelines.ingestion.sampler import sample_frames
from pipelines.ingestion.scene_builder import iter_scenes
from pipelines.ingestion.timeline import DecodeTimeline
from pipelines.ingestion.tracker import ObjectTracker, PassthroughTracker
from pipelines.ingestion.video_reader import acquire_video, decode_video, validate_video
from pipelines.ingestion.vlm_candidates import select_vlm_candidates
from repositories import corpus
from search.index import delete_by_video, preflight_points, reindex_video
from services.catalog_generation import invalidate_catalog


class DefaultPipelineRepository:
    get_video_for_pipeline = staticmethod(corpus.get_video_for_pipeline)
    insert_segments = staticmethod(corpus.insert_segments)
    delete_segments = staticmethod(corpus.delete_segments)
    mark_video_indexed = staticmethod(corpus.mark_video_indexed)
    preflight_segments = staticmethod(corpus.preflight_segments)


class DefaultPipelineIndexer:
    preflight = staticmethod(preflight_points)
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
    settings = get_settings()
    detector = get_yolo_privacy_detector(
        resolve_privacy_weights(settings.ml),
        settings.ml.privacy_yolo_confidence,
        settings.ml.privacy_yolo_image_size,
    )
    return PipelineDependencies(
        repository=DefaultPipelineRepository(),
        scene_indexer=DefaultPipelineIndexer(),
        raw_storage=get_raw_storage(),
        derived_storage=get_derived_storage(),
        encoder=get_qwen_encoder(),
        siglip_encoder=get_siglip_encoder(),
        privacy_detector=detector,
        tracker=PassthroughTracker(),
        behavior_detector=NoopBehaviorDetector(),
        settings=settings,
    )


async def _stage(progress: Any, value: int, name: str) -> None:
    if progress is not None:
        await progress(value, name)


async def run_ingestion_pipeline(
    *,
    job_id: str,
    video_id: str,
    pipeline_version: str = PIPELINE_VERSION,
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
    if video.ingested_at is not None and video.ingestion_status == "indexed":
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
    owned_frames: dict[int, Any] = {}
    scene_stream = None
    sampled = None
    decoded = None
    segments_replaced = False
    vectors_written = False
    published = False
    try:
        with ctx:
            await _stage(progress, 5, "acquire")
            stage_started = time.perf_counter()
            local_video = await acquire_video(ctx, deps.raw_storage)
            probe = validate_video(
                local_video,
                max_duration_s=deps.settings.video.max_duration_s,
                max_pixels=deps.settings.video.max_pixels,
            )
            ctx.metrics["acquire_duration_ms"] = round(
                (time.perf_counter() - stage_started) * 1000, 2
            )

            await _stage(progress, 15, "decode_sample_privacy")

            def own_frames(frames: Any) -> Any:
                try:
                    for frame in frames:
                        owned_frames[id(frame)] = frame
                        ctx.metrics["peak_active_frames"] = max(
                            ctx.metrics.get("peak_active_frames", 0), len(owned_frames)
                        )
                        yield frame
                finally:
                    if hasattr(frames, "close"):
                        frames.close()

            timeline = DecodeTimeline()
            decoded = decode_video(local_video, timeline=timeline)
            sampled = sample_frames(
                decoded,
                fps=deps.settings.video.sample_fps,
                max_gap_sec=deps.settings.video.sampling_max_gap_sec,
                video_end_ms=probe.end_ms if probe is not None else None,
                timeline=timeline,
            )
            safe = own_frames(verified_frames(anonymize_frames(sampled, deps.privacy_detector)))
            enriched = extract_metadata(safe)
            tracked = deps.tracker.track(enriched)
            behavior_frames = deps.behavior_detector.detect(tracked)
            await _stage(progress, 35, "siglip_embedding_scene_building")
            embedded_frames = iter_embedded_frames(
                behavior_frames,
                encoder=deps.siglip_encoder or deps.encoder,
                batch_size=deps.settings.ml.batch_size,
            )
            scene_stream = iter_scenes(
                embedded_frames,
                video_id=video_id,
                pipeline_version=pipeline_version,
                max_duration_sec=deps.settings.video.segment_seconds,
                gap_threshold_sec=deps.settings.video.segment_gap_tolerance_s,
                sample_interval_ms=max(1, round(1000 / deps.settings.video.sample_fps)),
                video_end_ms=probe.end_ms if probe is not None else None,
                settings=deps.settings.video,
            )
            scenes = []
            embeddings = []
            dedup = DedupStats()
            ctx.metrics["sampled_frames"] = 0
            ctx.metrics["embedding_batches"] = 0
            ctx.metrics["vlm_scenes_success"] = 0
            ctx.metrics["vlm_scenes_failed"] = 0
            ctx.metrics["vlm_scenes_partial"] = 0
            ctx.metrics["vlm_frames_selected"] = 0
            ctx.metrics["vlm_http_requests"] = 0
            ctx.metrics["vlm_scenes_not_configured"] = 0
            for scene in scene_stream:
                samples = list(scene.keyframes)
                ctx.metrics["sampled_frames"] += len(samples)
                try:
                    select_representative(scene)
                    scene.keyframes = list(
                        filter_near_duplicates(
                            samples,
                            enabled=deps.settings.video.dedup_enabled,
                            threshold=deps.settings.video.dedup_threshold,
                            stats=dedup,
                            close_dropped=False,
                        )
                    )
                    select_vlm_candidates(
                        scene,
                        samples,
                        deps.settings.video,
                    )
                    protected = {id(f) for f in scene.keyframes + scene.vlm_candidates}
                    for frame in samples:
                        if id(frame) not in protected:
                            frame.close()
                    await _stage(progress, 50, "qwen_embedding_retained")
                    embed_frames_qwen(
                        scene.keyframes,
                        encoder=deps.encoder,
                        batch_size=deps.settings.ml.batch_size,
                    )
                    await extract_scene_vlm_metadata([scene], settings=deps.settings)
                    enrichment = (scene.metadata.get("vlm_data") or {}).get("enrichment") or {}
                    status = enrichment.get("status", "failed")
                    counter = (
                        "success"
                        if status == "success"
                        else "partial"
                        if status == "partial"
                        else "not_configured"
                        if status == "not_configured"
                        else "failed"
                    )
                    ctx.metrics[f"vlm_scenes_{counter}"] += 1
                    ctx.metrics["vlm_frames_selected"] += len(scene.vlm_candidates)
                    ctx.metrics["vlm_http_requests"] += sum(
                        f.metadata.get("vlm_request_count", 0) for f in scene.vlm_candidates
                    )
                    embeddings.extend(
                        embed_scenes(
                            [scene],
                            encoder=deps.encoder,
                            qwen_encoder=deps.encoder if deps.siglip_encoder is not None else None,
                            siglip_encoder=deps.siglip_encoder,
                            expected_dimension=deps.settings.qdrant.vector_size,
                            model=deps.settings.ml.encoder_name,
                            version=deps.encoder.model_version,
                            batch_size=deps.settings.ml.batch_size,
                        )
                    )
                    stage_scene_thumbnail(ctx, scene)
                    ctx.metrics["embedding_batches"] += (
                        len(scene.keyframes) + deps.settings.ml.batch_size - 1
                    ) // deps.settings.ml.batch_size
                    scenes.append(scene)
                finally:
                    for frame in samples:
                        frame.close()
                        frame.embedding = frame.qwen_embedding = None
                        owned_frames.pop(id(frame), None)
            if not scenes:
                raise PipelineError("Pipeline produced no privacy-safe scenes", stage="privacy")
            ctx.metrics["retained_frames"] = dedup.kept
            ctx.metrics["dedup_seen"] = dedup.seen
            ctx.metrics["dedup_dropped"] = dedup.dropped
            ctx.metrics["dedup_drop_ratio"] = round(dedup.drop_ratio, 6)
            ctx.metrics["scenes_created"] = len(scenes)

            await _stage(progress, 80, "preview_generation")
            uploaded = await generate_previews(
                ctx,
                scenes,
                deps.derived_storage,
                source_video=local_video,
                detector=deps.privacy_detector,
            )

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
                    representative_frame_index=scene.representative_frame.frame_index,
                    representative_timestamp_ms=scene.representative_frame.timestamp_ms,
                    thumbnail_object_key=scene.thumbnail_key,
                    embedding_model=deps.settings.ml.encoder_name,
                    model_version=deps.encoder.model_version,
                )
                for index, scene in enumerate(scenes)
            ]
            points = build_scene_points(scenes, embeddings, dataset=video.dataset)
            await deps.repository.preflight_segments(video_uuid, rows)
            await deps.scene_indexer.preflight(points)
            try:
                await deps.repository.delete_segments(video_uuid)
                segments_replaced = True
                await deps.repository.insert_segments(video_uuid, rows)
                written = await persist_vectors(video_id, points, deps.scene_indexer)
                vectors_written = True
                indexed = await deps.repository.mark_video_indexed(
                    video_uuid,
                    model_version=deps.encoder.model_version,
                    preview_object_key=scenes[0].preview_key,
                )
                if indexed is False:
                    raise PipelineError(
                        "Video ingestion was cancelled during persistence",
                        stage="persistence",
                    )
                published = True
                await invalidate_catalog()
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
                "previews_created": 1,
                "thumbnails_created": len(scenes),
                "metrics": dict(ctx.metrics),
                "pipeline_version": pipeline_version,
                "metadata_status": (
                    "success"
                    if ctx.metrics["vlm_scenes_success"] == len(scenes)
                    else "not_configured"
                    if ctx.metrics["vlm_scenes_not_configured"] == len(scenes)
                    else "partial"
                    if ctx.metrics["vlm_scenes_success"] or ctx.metrics["vlm_scenes_partial"]
                    else "failed"
                ),
            }
    except Exception as exc:
        stage = exc.stage if isinstance(exc, PipelineError) else "unknown"
        logger.bind(job_id=job_id, video_id=video_id, stage=stage).exception(
            "Ingestion pipeline failed: {error_type}", error_type=type(exc).__name__
        )
        # Keep published media if final progress reporting fails.
        if published:
            raise
        if segments_replaced or vectors_written:
            cleanup = []
            if vectors_written:
                cleanup.append(("Qdrant points", deps.scene_indexer.delete_by_video(video_id)))
            if segments_replaced:
                cleanup.append(("PostgreSQL segments", deps.repository.delete_segments(video_uuid)))
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
        if scene_stream is not None:
            scene_stream.close()
        if sampled is not None:
            sampled.close()
        if decoded is not None and hasattr(decoded, "close"):
            decoded.close()
        for frame in owned_frames.values():
            frame.close()


__all__ = ["PipelineDependencies", "default_dependencies", "run_ingestion_pipeline"]
