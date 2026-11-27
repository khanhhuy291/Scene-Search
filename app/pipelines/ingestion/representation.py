"""Build the shared SQL/Qdrant representation without running model inference."""

from uuid import UUID, uuid5

from qdrant_client import models

from core.privacy import THUMBNAIL_VERSION
from pipelines.common.context import PipelineContext
from pipelines.common.types import FrameRecord, IndexedKeyframe, SceneRecord
from pipelines.ingestion.indexer import build_scene_points
from pipelines.ingestion.scene_builder import SCENE_NAMESPACE
from pipelines.ingestion.vector_index import RepresentationPoints
from repositories.corpus import SegmentRow
from repositories.scene_graph import MembershipRow, SceneGraph, SceneKeyframeRow, SemanticSceneRow


def _indexed_frames(chunk: SceneRecord) -> list[FrameRecord]:
    frames = list(
        {frame.frame_index: frame for frame in [*chunk.keyframes, *chunk.vlm_candidates]}.values()
    )
    representative = chunk.representative_frame
    if representative is not None and all(
        frame.frame_index != representative.frame_index for frame in frames
    ):
        frames.append(representative)
    return sorted(frames, key=lambda frame: (frame.timestamp_ms, frame.frame_index))


def collect_keyframes(
    ctx: PipelineContext,
    chunk: SceneRecord,
    records: dict[int, IndexedKeyframe],
    fingerprint: str,
) -> list[tuple[IndexedKeyframe, FrameRecord]]:
    added = []
    for frame in _indexed_frames(chunk):
        if frame.embedding is None or frame.privacy_status != "verified":
            raise ValueError("Indexing requires a verified, embedded keyframe")
        record = records.get(frame.frame_index)
        parent_id = chunk.metadata["semantic_scene_id"]
        if record is None:
            identifier = str(
                uuid5(
                    SCENE_NAMESPACE,
                    f"{ctx.video_id}:{fingerprint}:{ctx.job_id}:frame:{frame.frame_index}",
                )
            )
            record = IndexedKeyframe(
                identifier,
                ctx.video_id,
                parent_id,
                frame.frame_index,
                frame.timestamp_ms,
                frame.embedding,
                f"videos/{ctx.video_id}/keyframes/{identifier}/thumbnail-{THUMBNAIL_VERSION}/{ctx.job_id}.jpg",
            )
            records[frame.frame_index] = record
            added.append((record, frame))
        if record.semantic_scene_id != parent_id or record.timestamp_ms != frame.timestamp_ms:
            raise ValueError("Keyframe reference crosses semantic scenes")
        if chunk.scene_id not in record.chunk_ids:
            record.chunk_ids.append(chunk.scene_id)
    representative = chunk.representative_frame
    if representative is None or representative.frame_index not in records:
        raise ValueError("Chunk representative must be an indexed keyframe")
    chunk.thumbnail_key = records[representative.frame_index].thumbnail_key
    return added


def build_scene_graph(
    video_id,
    run_id,
    fingerprint,
    semantic_scenes,
    chunks,
    keyframes,
    *,
    model,
    model_version,
):
    parents = tuple(
        SemanticSceneRow(
            UUID(scene.scene_id),
            index,
            scene.start_ms / 1000,
            scene.end_ms / 1000,
            scene.boundary_reason,
            scene.boundary_score,
            fingerprint,
        )
        for index, scene in enumerate(semantic_scenes)
    )
    rows = tuple(
        SegmentRow(
            index,
            chunk.start_ms / 1000,
            chunk.end_ms / 1000,
            len(_indexed_frames(chunk)),
            id=UUID(chunk.scene_id),
            semantic_scene_id=UUID(chunk.metadata["semantic_scene_id"]),
            preview_object_key=chunk.preview_key,
            thumbnail_object_key=chunk.thumbnail_key,
            privacy_status=chunk.privacy_status,
            ingestion_fingerprint=fingerprint,
            representative_frame_index=chunk.representative_frame.frame_index,
            representative_timestamp_ms=chunk.representative_frame.timestamp_ms,
            embedding_model=model,
            model_version=model_version,
        )
        for index, chunk in enumerate(chunks)
    )
    frames = tuple(
        SceneKeyframeRow(
            UUID(frame.keyframe_id),
            UUID(frame.semantic_scene_id),
            frame.frame_index,
            frame.timestamp_ms,
            frame.thumbnail_key,
            "verified",
            fingerprint,
        )
        for frame in keyframes
    )
    by_index = {frame.frame_index: frame for frame in keyframes}
    links = tuple(
        MembershipRow(
            UUID(chunk.scene_id),
            UUID(by_index[frame.frame_index].keyframe_id),
            frame.frame_index == chunk.representative_frame.frame_index,
        )
        for chunk in chunks
        for frame in _indexed_frames(chunk)
    )
    return SceneGraph(UUID(video_id), run_id, fingerprint, parents, rows, frames, links)


def build_representation_points(
    chunks,
    embeddings,
    keyframes,
    *,
    dataset,
    fingerprint,
    run_id,
    siglip_version,
    vector_dimensions=None,
):
    points = build_scene_points(chunks, embeddings, dataset=dataset)
    by_index = {frame.frame_index: frame for frame in keyframes}
    for chunk, point in zip(chunks, points, strict=True):
        point.id = chunk.scene_id
        point.payload.update(
            chunk_id=chunk.scene_id,
            semantic_scene_id=chunk.metadata["semantic_scene_id"],
            semantic_start_ms=chunk.metadata["semantic_start_ms"],
            semantic_end_ms=chunk.metadata["semantic_end_ms"],
            boundary_reason=chunk.metadata["boundary_reason"],
            boundary_score=chunk.metadata.get("boundary_score"),
            keyframe_ids=[
                by_index[frame.frame_index].keyframe_id for frame in _indexed_frames(chunk)
            ],
            vlm_frame_ids=[
                by_index[frame.frame_index].keyframe_id for frame in chunk.vlm_candidates
            ],
            ingestion_fingerprint=fingerprint,
            ingestion_run_id=run_id,
            caption_embedding_status=chunk.metadata["caption_embedding_status"],
            siglip_embedding_version=siglip_version,
            qwen_embedding_version=point.payload["embedding_version"],
            caption_embedding_version=point.payload["embedding_version"]
            if "caption" in point.vector
            else None,
        )
    frame_points = tuple(
        models.PointStruct(
            id=frame.keyframe_id,
            vector={"siglip": frame.embedding},
            payload={
                "video_id": frame.video_id,
                "dataset": dataset,
                "granularity": "frame",
                "keyframe_id": frame.keyframe_id,
                "frame_id": frame.frame_index,
                "semantic_scene_id": frame.semantic_scene_id,
                "chunk_ids": frame.chunk_ids,
                "timestamp_ms": frame.timestamp_ms,
                "ts_start_s": frame.timestamp_ms / 1000,
                "ts_end_s": frame.timestamp_ms / 1000,
                "video_second": frame.timestamp_ms / 1000,
                "thumbnail_key": frame.thumbnail_key,
                "minio_path": frame.thumbnail_key,
                "video_key": chunks[0].preview_key,
                "privacy_status": "verified",
                "playback_anonymized": True,
                "ingestion_fingerprint": fingerprint,
                "ingestion_run_id": run_id,
                "embedding_model": "siglip",
                "model_version": siglip_version,
            },
        )
        for frame in keyframes
    )
    dimensions = vector_dimensions or {
        "siglip": len(points[0].vector["siglip"]),
        "qwen": len(points[0].vector["qwen"]),
        "caption": len(points[0].vector["qwen"]),
    }
    return RepresentationPoints(tuple(points), frame_points, run_id, fingerprint, dimensions)
