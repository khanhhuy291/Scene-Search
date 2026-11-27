"""Deterministic, privacy-safe scene keyframes in SigLIP space."""

from __future__ import annotations

import math

from PIL import ImageFilter, ImageStat

from core.config import VideoSettings
from ml.vectors import cosine, normalize_vectors
from pipelines.common.types import FrameRecord, SceneRecord


def _image_quality(frame: FrameRecord) -> float:
    """Bounded sharpness relative to contrast, without rejecting dark scenes."""
    with frame.display_image.convert("L") as image:
        image.thumbnail((128, 128))
        if min(image.size) < 3:
            return 0.0
        with (
            image.filter(ImageFilter.FIND_EDGES) as edges,
            edges.crop((1, 1, image.width - 1, image.height - 1)) as interior,
        ):
            sharpness = ImageStat.Stat(interior).var[0]
        contrast = ImageStat.Stat(image).var[0]
    relative_sharpness = sharpness / (contrast + 1.0)
    return relative_sharpness / (relative_sharpness + 1.0)


def _select_frames(
    candidates: list[FrameRecord],
    representative: FrameRecord,
    *,
    scene: SceneRecord,
    scores: dict[int, float],
    quality: dict[int, float],
    min_frames: int,
    max_frames: int,
    novelty_distance: float,
    quality_weight: float,
) -> list[FrameRecord]:
    selected = [representative]
    remaining = [f for f in candidates if f.frame_index != representative.frame_index]
    duration = scene.end_ms - scene.start_ms

    def region(frame: FrameRecord) -> int:
        return (frame.timestamp_ms - scene.start_ms) * min_frames // duration

    # Fill temporal regions first. Even near-identical samples may be needed
    # here; novelty is enforced only for additional, discretionary frames.
    while remaining and len(selected) < min(min_frames, max_frames):
        occupied = {region(frame) for frame in selected}
        uncovered = [frame for frame in remaining if region(frame) not in occupied]
        chosen = max(
            uncovered or remaining,
            key=lambda frame: (
                min(abs(frame.timestamp_ms - other.timestamp_ms) for other in selected)
                if not uncovered
                else scores[frame.frame_index],
                -abs(
                    frame.timestamp_ms
                    - (scene.start_ms + (region(frame) + 0.5) * duration / min_frames)
                ),
                -frame.timestamp_ms,
                -frame.frame_index,
            ),
        )
        selected.append(chosen)
        remaining = [f for f in remaining if f.frame_index != chosen.frame_index]

    while remaining and len(selected) < max_frames:
        novelty = {
            frame.frame_index: min(
                1 - cosine(frame.embedding, other.embedding) for other in selected
            )
            for frame in remaining
        }
        eligible = [f for f in remaining if novelty[f.frame_index] > novelty_distance]
        if not eligible:
            break
        chosen = max(
            eligible,
            key=lambda frame: (
                novelty[frame.frame_index] + quality_weight * quality[frame.frame_index],
                min(abs(frame.timestamp_ms - other.timestamp_ms) for other in selected),
                scores[frame.frame_index],
                -frame.timestamp_ms,
                -frame.frame_index,
            ),
        )
        selected.append(chosen)
        remaining = [f for f in remaining if f.frame_index != chosen.frame_index]
    return sorted(selected, key=lambda frame: (frame.timestamp_ms, frame.frame_index))


def select_keyframes(
    scene: SceneRecord, samples: list[FrameRecord], settings: VideoSettings
) -> None:
    """Select Qwen, VLM and thumbnail references without changing sample coverage."""
    if scene.end_ms <= scene.start_ms:
        raise ValueError("Scene timestamps are invalid")
    by_index: dict[int, FrameRecord] = {}
    for frame in samples:
        if not scene.start_ms <= frame.timestamp_ms < scene.end_ms:
            raise ValueError("Keyframe timestamp is outside the scene")
        if frame.privacy_status != "verified" or frame.display_image is None:
            continue
        previous = by_index.get(frame.frame_index)
        if previous is not None and previous is not frame:
            raise ValueError("Conflicting keyframe references for the same frame index")
        by_index[frame.frame_index] = frame
    candidates = sorted(
        by_index.values(), key=lambda frame: (frame.timestamp_ms, frame.frame_index)
    )
    if not candidates:
        raise ValueError("Scene has no verified representative derivative")
    if any(frame.embedding is None for frame in candidates):
        raise ValueError("Keyframe selection requires SigLIP embeddings")
    dimension = len(candidates[0].embedding)
    vectors = normalize_vectors([frame.embedding for frame in candidates], dimension=dimension)
    centroid = normalize_vectors(
        [[math.fsum(vector[i] for vector in vectors) for i in range(dimension)]],
        dimension=dimension,
    )[0]
    quality = {frame.frame_index: _image_quality(frame) for frame in candidates}
    scores = {
        frame.frame_index: cosine(vector, centroid)
        + settings.keyframe_quality_weight * quality[frame.frame_index]
        for frame, vector in zip(candidates, vectors, strict=True)
    }
    midpoint = (scene.start_ms + scene.end_ms) / 2
    representative = max(
        candidates,
        key=lambda frame: (
            scores[frame.frame_index],
            -abs(frame.timestamp_ms - midpoint),
            -frame.timestamp_ms,
            -frame.frame_index,
        ),
    )
    qwen_frames = _select_frames(
        candidates,
        representative,
        scene=scene,
        scores=scores,
        quality=quality,
        min_frames=settings.keyframe_min_frames,
        max_frames=settings.keyframe_max_frames,
        novelty_distance=settings.keyframe_novelty_distance,
        quality_weight=settings.keyframe_quality_weight,
    )
    vlm_frames = _select_frames(
        candidates,
        representative,
        scene=scene,
        scores=scores,
        quality=quality,
        min_frames=min(settings.vlm_min_frames, settings.vlm_max_frames),
        max_frames=settings.vlm_max_frames,
        novelty_distance=settings.vlm_novelty_distance
        if settings.vlm_novelty_distance is not None
        else settings.keyframe_novelty_distance,
        quality_weight=settings.keyframe_quality_weight,
    )
    scene.keyframes = qwen_frames
    scene.vlm_candidates = vlm_frames
    scene.representative_frame = representative
