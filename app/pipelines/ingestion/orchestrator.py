"""The single coordinator for the production ingestion stage order."""

from __future__ import annotations

import asyncio
import time
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, replace
from typing import Any, Protocol
from uuid import UUID

from loguru import logger

from core.config import Settings, get_settings
from db.models.corpus import Video
from infrastructure.minio import MinIOStorage, get_derived_storage, get_raw_storage
from ml.anonymize import BlurRegionDetector
from ml.encoder import Encoder, get_qwen_encoder, get_siglip_encoder
from ml.privacy_weights import resolve_privacy_weights
from ml.yolo_privacy import get_yolo_privacy_detector
from pipelines.common.context import PipelineContext
from pipelines.common.errors import (
    PersistenceError,
    PipelineError,
    RetryablePersistenceError,
    VideoAcquireError,
)
from pipelines.common.types import IndexedKeyframe, SemanticScene
from pipelines.ingestion.anonymizer import anonymize_frames
from pipelines.ingestion.chunk_builder import iter_chunks
from pipelines.ingestion.embedder import embed_frames_qwen, embed_scenes, iter_embedded_frames
from pipelines.ingestion.frame_store import FrameStore
from pipelines.ingestion.identity import ingestion_fingerprint, ingestion_snapshot
from pipelines.ingestion.indexer import persist_vectors
from pipelines.ingestion.keyframe_selector import select_keyframes
from pipelines.ingestion.metadata_extractor import (
    VLMRequestCache,
    extract_metadata,
    extract_scene_vlm_metadata,
)
from pipelines.ingestion.preview_generator import generate_previews, stage_keyframe_thumbnail
from pipelines.ingestion.privacy_verifier import verified_frames
from pipelines.ingestion.representation import (
    build_representation_points,
    build_scene_graph,
    collect_keyframes,
)
from pipelines.ingestion.sampler import sample_frames
from pipelines.ingestion.scene_builder import iter_semantic_scenes
from pipelines.ingestion.timeline import DecodeTimeline
from pipelines.ingestion.vector_index import RepresentationPoints, SceneVectorIndexer
from pipelines.ingestion.video_reader import acquire_video, decode_video, validate_video
from repositories import corpus, scene_graph
from services.catalog_generation import invalidate_catalog


class PipelineRepository(Protocol):
    def ingestion_lease(self, video_id: UUID) -> AbstractAsyncContextManager[None]: ...
    async def get_video_for_pipeline(self, video_id: UUID) -> Video | None: ...
    async def preflight_scene_graph(
        self, graph: scene_graph.SceneGraph, *, max_duration_s: float
    ) -> None: ...
    async def reserve_scene_publication(self, graph: scene_graph.SceneGraph) -> None: ...
    async def publish_scene_graph(
        self, graph: scene_graph.SceneGraph, *, model_version: str
    ) -> None: ...
    async def serving_media(self, video_id: UUID) -> set[str]: ...
    async def assert_ingestion_owner(self, video_id: UUID, run_id: str) -> None: ...
    async def owns_scene_graph(self, video_id: UUID, run_id: str) -> bool: ...


class PipelineIndexer(Protocol):
    async def preflight_models(self, dimensions: dict[str, int]) -> None: ...
    async def preflight(self, batch: RepresentationPoints) -> None: ...
    async def reindex_video(self, video_id: str, batch: RepresentationPoints) -> int: ...
    async def delete_by_video(self, video_id: str, *, run_id: str | None = None) -> None: ...


class DefaultPipelineRepository:
    ingestion_lease = staticmethod(scene_graph.ingestion_lease)
    get_video_for_pipeline = staticmethod(corpus.get_video_for_pipeline)
    preflight_scene_graph = staticmethod(scene_graph.preflight_scene_graph)
    reserve_scene_publication = staticmethod(scene_graph.reserve_scene_publication)
    publish_scene_graph = staticmethod(scene_graph.publish_scene_graph)
    serving_media = staticmethod(scene_graph.serving_media)
    assert_ingestion_owner = staticmethod(scene_graph.assert_ingestion_owner)
    owns_scene_graph = staticmethod(scene_graph.owns_scene_graph)


@dataclass
class PipelineDependencies:
    repository: PipelineRepository
    scene_indexer: PipelineIndexer
    raw_storage: MinIOStorage
    derived_storage: MinIOStorage
    encoder: Encoder
    privacy_detector: BlurRegionDetector
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
        scene_indexer=SceneVectorIndexer(settings.qdrant),
        raw_storage=get_raw_storage(),
        derived_storage=get_derived_storage(),
        encoder=get_qwen_encoder(),
        siglip_encoder=get_siglip_encoder(),
        privacy_detector=detector,
        settings=settings,
    )


async def _stage(progress: Any, value: int, name: str) -> None:
    if progress is not None:
        await progress(value, name)


async def run_ingestion_pipeline(
    *,
    job_id: str,
    video_id: str,
    progress: Any = None,
    dependencies: PipelineDependencies | None = None,
) -> dict[str, Any]:
    """Acquire a registered MinIO video and produce persisted, searchable scenes."""
    deps = dependencies or default_dependencies()
    async with deps.repository.ingestion_lease(UUID(video_id)):
        return await _run_ingestion_pipeline(
            job_id=job_id, video_id=video_id, progress=progress, deps=deps
        )


async def _run_ingestion_pipeline(
    *, job_id: str, video_id: str, progress: Any, deps: PipelineDependencies
) -> dict[str, Any]:
    started = time.perf_counter()
    video_uuid = UUID(video_id)
    video = await deps.repository.get_video_for_pipeline(video_uuid)
    if video is None:
        raise VideoAcquireError(f"Video {video_id} does not exist", stage="acquire")
    if not video.raw_object_key:
        raise VideoAcquireError(f"Video {video_id} has no raw object", stage="acquire")
    fingerprint = ingestion_fingerprint(
        video.checksum,
        deps.settings,
        qwen_version=deps.encoder.model_version,
        siglip_version=(deps.siglip_encoder or deps.encoder).model_version,
    )
    if video.ingested_at is not None and video.ingestion_status == "indexed":
        if video.ingestion_fingerprint != fingerprint:
            raise PipelineError(
                "Indexed video requires explicit re-ingestion for the changed representation",
                stage="acquire",
            )
        return {"video_id": video_id, "duplicate": True, "scenes_indexed": 0}
    ingestion_identity = f"{fingerprint}:{job_id}"
    await deps.repository.assert_ingestion_owner(video_uuid, job_id)
    vector_dimensions = {
        "siglip": (deps.siglip_encoder or deps.encoder).dimension,
        "qwen": deps.encoder.dimension,
        "caption": deps.encoder.dimension,
    }
    await deps.scene_indexer.preflight_models(vector_dimensions)
    previous_run = getattr(video, "active_ingestion_run_id", None)
    previous_media = await deps.repository.serving_media(video_uuid) if previous_run else set()

    ctx = PipelineContext(
        job_id=job_id,
        video_id=video_id,
        raw_minio_key=video.raw_object_key,
        source_checksum=video.checksum,
        embedding_model=deps.settings.ml.encoder_name,
        settings=deps.settings,
    )
    uploaded: list[str] = []
    owned_frames: dict[int, Any] = {}
    vlm_request_cache = VLMRequestCache()
    frame_store: FrameStore | None = None
    semantic_scenes: list[SemanticScene] = []
    indexed_keyframes: dict[int, IndexedKeyframe] = {}
    scene_stream = None
    sampled = None
    decoded = None
    publication_reserved = False
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
            decoded = ctx.timed_frames(decode_video(local_video, timeline=timeline), "decode")
            sampled = sample_frames(
                decoded,
                fps=deps.settings.video.sample_fps,
                max_gap_sec=deps.settings.video.sampling_max_gap_sec,
                video_end_ms=probe.end_ms if probe is not None else None,
                timeline=timeline,
            )
            sampled = ctx.timed_frames(sampled, "sampling")
            safe = own_frames(
                ctx.timed_frames(
                    verified_frames(anonymize_frames(sampled, deps.privacy_detector)), "privacy"
                )
            )
            enriched = extract_metadata(safe)
            await _stage(progress, 35, "siglip_embedding_scene_building")
            embedded_frames = iter_embedded_frames(
                enriched,
                encoder=deps.siglip_encoder or deps.encoder,
                batch_size=deps.settings.ml.batch_size,
            )
            embedded_frames = ctx.timed_frames(embedded_frames, "siglip")
            frame_store = FrameStore(ctx.open_temp_dir() / "frames")

            def staged_frames():
                try:
                    for frame in embedded_frames:
                        frame_store.stage(frame)
                        owned_frames.pop(id(frame), None)
                        ctx.metrics["sampled_frames"] += 1
                        yield frame
                finally:
                    embedded_frames.close()

            def semantic_chunks():
                semantic_stream = iter_semantic_scenes(
                    staged_frames(),
                    video_id=video_id,
                    ingestion_identity=ingestion_identity,
                    settings=deps.settings.video,
                    sample_interval_ms=max(1, round(1000 / deps.settings.video.sample_fps)),
                    video_end_ms=probe.end_ms if probe is not None else None,
                    diagnostics=ctx.metrics,
                )
                try:
                    for semantic_scene in semantic_stream:
                        ctx.metrics["semantic_scenes_created"] += 1
                        semantic_scenes.append(semantic_scene)
                        yield from iter_chunks(
                            semantic_scene,
                            duration_s=deps.settings.video.retrieval_chunk_duration_s,
                            stride_s=deps.settings.video.retrieval_chunk_stride_s,
                            ingestion_identity=ingestion_identity,
                            diagnostics=ctx.metrics,
                        )
                finally:
                    semantic_stream.close()

            scene_stream = semantic_chunks()
            scenes = []
            embeddings = []
            ctx.metrics["sampled_frames"] = 0
            ctx.metrics["semantic_scenes_created"] = 0
            ctx.metrics["retained_frames"] = 0
            ctx.metrics["embedding_batches"] = 0
            ctx.metrics["vlm_scenes_success"] = 0
            ctx.metrics["vlm_scenes_failed"] = 0
            ctx.metrics["vlm_scenes_partial"] = 0
            ctx.metrics["vlm_frames_selected"] = 0
            ctx.metrics["vlm_http_requests"] = 0
            ctx.metrics["vlm_scenes_not_configured"] = 0
            for scene in scene_stream:
                samples = list(scene.keyframes)
                try:
                    frame_store.load(samples)
                    ctx.metrics["peak_active_frames"] = max(
                        ctx.metrics["peak_active_frames"], len(samples) + len(owned_frames)
                    )
                    with ctx.measure("keyframe_selection"):
                        select_keyframes(scene, samples, deps.settings.video)
                    ctx.metrics["retained_frames"] += len(scene.keyframes)
                    protected = {id(f) for f in scene.keyframes + scene.vlm_candidates}
                    protected.add(id(scene.representative_frame))
                    for frame in samples:
                        if id(frame) not in protected:
                            frame.close()
                    await _stage(progress, 50, "qwen_embedding_retained")
                    pending_qwen = sum(frame.qwen_embedding is None for frame in scene.keyframes)
                    ctx.metrics["qwen_frames_encoded"] = (
                        ctx.metrics.get("qwen_frames_encoded", 0) + pending_qwen
                    )
                    ctx.metrics["qwen_cache_hits"] = (
                        ctx.metrics.get("qwen_cache_hits", 0) + len(scene.keyframes) - pending_qwen
                    )
                    with ctx.measure("qwen"):
                        embed_frames_qwen(
                            scene.keyframes,
                            encoder=deps.encoder,
                            batch_size=deps.settings.ml.batch_size,
                            reuse_existing=True,
                        )
                    with ctx.measure("vlm"):
                        await extract_scene_vlm_metadata(
                            [scene], settings=deps.settings, request_cache=vlm_request_cache
                        )
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
                    ctx.metrics["vlm_http_requests"] += scene.metadata.get("vlm_request_count", 0)
                    embeddings.extend(
                        embed_scenes(
                            [scene],
                            qwen_encoder=deps.encoder,
                            siglip_encoder=deps.siglip_encoder or deps.encoder,
                            caption_encoder=deps.encoder,
                            version=deps.encoder.model_version,
                            metrics=ctx.metrics,
                            batch_size=deps.settings.ml.batch_size,
                        )
                    )
                    for keyframe, frame in collect_keyframes(
                        ctx, scene, indexed_keyframes, fingerprint
                    ):
                        stage_keyframe_thumbnail(ctx, keyframe, frame)
                    ctx.metrics["embedding_batches"] += (
                        pending_qwen + deps.settings.ml.batch_size - 1
                    ) // deps.settings.ml.batch_size
                    scenes.append(scene)
                finally:
                    for frame in samples:
                        frame.close()
                        owned_frames.pop(id(frame), None)
            if not scenes:
                raise PipelineError("Pipeline produced no privacy-safe scenes", stage="privacy")
            ctx.metrics["scenes_created"] = len(scenes)

            await _stage(progress, 80, "preview_generation")
            with ctx.measure("media_generation"):
                uploaded = await generate_previews(
                    ctx,
                    scenes,
                    deps.derived_storage,
                    source_video=local_video,
                    detector=deps.privacy_detector,
                    keyframes=list(indexed_keyframes.values()),
                )

            await _stage(progress, 85, "persistence")
            graph = build_scene_graph(
                video_id,
                job_id,
                fingerprint,
                semantic_scenes,
                scenes,
                list(indexed_keyframes.values()),
                model=deps.settings.ml.encoder_name,
                model_version=deps.encoder.model_version,
            )
            points = build_representation_points(
                scenes,
                embeddings,
                list(indexed_keyframes.values()),
                dataset=video.dataset,
                fingerprint=fingerprint,
                run_id=job_id,
                siglip_version=(deps.siglip_encoder or deps.encoder).model_version,
                vector_dimensions=vector_dimensions,
            )
            graph = replace(
                graph,
                snapshot=ingestion_snapshot(
                    deps.settings,
                    qwen_version=deps.encoder.model_version,
                    siglip_version=(deps.siglip_encoder or deps.encoder).model_version,
                ),
            )
            await deps.repository.preflight_scene_graph(
                graph,
                max_duration_s=deps.settings.video.retrieval_chunk_duration_s,
            )
            await deps.scene_indexer.preflight(points)
            try:
                await deps.repository.reserve_scene_publication(graph)
                publication_reserved = True
                with ctx.measure("vector_persistence"):
                    written = await persist_vectors(video_id, points, deps.scene_indexer)
                vectors_written = True
                with ctx.measure("publication"):
                    await deps.repository.publish_scene_graph(
                        graph, model_version=deps.encoder.model_version
                    )
                published = True
                await invalidate_catalog()
                try:
                    if previous_run and previous_run != job_id:
                        await deps.scene_indexer.delete_by_video(video_id, run_id=previous_run)
                        for key in previous_media - set(uploaded):
                            await asyncio.to_thread(deps.derived_storage.delete_object, key)
                except Exception:
                    logger.exception("Could not remove superseded vectors for {}", video_id)
            except Exception as exc:
                if isinstance(exc, PipelineError):
                    raise
                if isinstance(exc, ValueError):
                    raise PersistenceError(
                        "Publication validation failed", stage="persistence"
                    ) from exc
                raise RetryablePersistenceError(
                    "Unable to persist scene metadata", stage="persistence"
                ) from exc

            ctx.metrics["qdrant_points_upserted"] = written
            ctx.metrics["sampled_frames_total"] = ctx.metrics.get("sampling_frames", 0)
            ctx.metrics["privacy_rejected_frames"] = max(
                0, ctx.metrics.get("sampling_frames", 0) - ctx.metrics.get("privacy_frames", 0)
            )
            ctx.metrics["keyframes_indexed"] = len(indexed_keyframes)
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
                "thumbnails_created": len(indexed_keyframes),
                "keyframes_indexed": len(indexed_keyframes),
                "ingestion_fingerprint": fingerprint,
                "metrics": dict(ctx.metrics),
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
    except (Exception, asyncio.CancelledError) as exc:
        stage = exc.stage if isinstance(exc, PipelineError) else "unknown"
        logger.bind(job_id=job_id, video_id=video_id, stage=stage).exception(
            "Ingestion pipeline failed: {error_type}", error_type=type(exc).__name__
        )
        # Keep published media if final progress reporting fails.
        if published:
            raise
        if publication_reserved or vectors_written:
            cleanup = []
            try:
                owned = await deps.repository.owns_scene_graph(video_uuid, job_id)
            except Exception:
                logger.exception(
                    "Could not verify publication ownership; retaining media for retry"
                )
                owned = False
            if not owned:
                uploaded = []
            if owned:
                cleanup.append(
                    ("Qdrant points", deps.scene_indexer.delete_by_video(video_id, run_id=job_id))
                )
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
        if frame_store is not None:
            frame_store.close()


__all__ = ["PipelineDependencies", "default_dependencies", "run_ingestion_pipeline"]
