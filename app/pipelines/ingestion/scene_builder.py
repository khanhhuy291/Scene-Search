"""Construct semantic scenes from a sampled embedding timeline."""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterable, Iterator

from core.config import VideoSettings
from ml.vectors import normalize_vectors
from pipelines.common.types import FrameRecord, SemanticScene
from pipelines.ingestion.boundary_refiner import refine_boundaries
from pipelines.ingestion.semantic_segmenter import detect_boundaries

SCENE_NAMESPACE = uuid.UUID("babfb50b-01e3-49cd-8d69-b34a5d20c574")


def _has_gap(previous: FrameRecord, frame: FrameRecord, gap_ms: int) -> bool:
    old_sequence = previous.metadata.get("sample_sequence")
    sequence = frame.metadata.get("sample_sequence")
    if old_sequence is not None and sequence is not None and sequence != old_sequence + 1:
        return True
    # Normal sample cadence/PTS rounding is not lost data. Measure only the
    # uncovered interval, without extending the previous sample's coverage.
    covered_until = previous.timestamp_ms
    if previous.covers_end_ms is not None and previous.covers_end_ms > previous.timestamp_ms:
        covered_until = previous.covers_end_ms
    return frame.timestamp_ms - covered_until > gap_ms


def iter_semantic_scenes(
    frames: Iterable[FrameRecord],
    *,
    video_id: str,
    ingestion_identity: str,
    settings: VideoSettings,
    sample_interval_ms: int,
    video_end_ms: int | None = None,
    diagnostics: dict | None = None,
) -> Iterator[SemanticScene]:
    """Group a lightweight embedding timeline, refining each continuity span separately."""
    span: list[FrameRecord] = []
    reason = "video_start"
    dimension: int | None = None
    seen_indices: set[int] = set()
    gap_ms = round(settings.segment_gap_tolerance_s * 1000)

    def finish(limit_ms: int | None = None) -> Iterator[SemanticScene]:
        started = time.perf_counter()
        details = {}
        candidates = detect_boundaries(span, settings, diagnostics=details)
        if diagnostics is not None:
            diagnostics["segmentation_duration_ms"] = (
                diagnostics.get("segmentation_duration_ms", 0)
                + (time.perf_counter() - started) * 1000
            )
        started = time.perf_counter()
        boundaries = refine_boundaries(span, candidates, settings)
        if diagnostics is not None:
            diagnostics["refinement_duration_ms"] = (
                diagnostics.get("refinement_duration_ms", 0)
                + (time.perf_counter() - started) * 1000
            )
            for key, count in (
                ("boundary_candidates", len(candidates)),
                ("boundaries_retained", len(boundaries)),
                ("boundaries_removed", len(candidates) - len(boundaries)),
                ("unavailable_window_scores", details.get("unavailable_scores", 0)),
            ):
                diagnostics[key] = diagnostics.get(key, 0) + count
            if "threshold" in details:
                diagnostics["last_boundary_threshold"] = details["threshold"]
        offsets = [0, *(boundary.frame_offset for boundary in boundaries), len(span)]
        last = span[-1]
        coverage_end = last.covers_end_ms
        if coverage_end is None or coverage_end <= last.timestamp_ms:
            coverage_end = last.timestamp_ms + max(1, sample_interval_ms)
        if video_end_ms is not None:
            coverage_end = min(coverage_end, video_end_ms)
        if limit_ms is not None:
            coverage_end = min(coverage_end, limit_ms)
        for index, (start, end) in enumerate(zip(offsets, offsets[1:])):
            start_ms = span[start].timestamp_ms
            end_ms = span[end].timestamp_ms if end < len(span) else coverage_end
            yield SemanticScene(
                scene_id=str(
                    uuid.uuid5(
                        SCENE_NAMESPACE,
                        f"{video_id}:{ingestion_identity}:semantic:{start_ms}:{end_ms}",
                    )
                ),
                video_id=video_id,
                start_ms=start_ms,
                end_ms=end_ms,
                frames=tuple(span[start:end]),
                boundary_reason="semantic_change" if index else reason,
                boundary_score=boundaries[index - 1].score if index else None,
            )

    source = iter(frames)
    try:
        for frame in source:
            if frame.timestamp_ms < 0:
                raise ValueError("Semantic sample timestamp must be nonnegative")
            if video_end_ms is not None and frame.timestamp_ms >= video_end_ms:
                raise ValueError("Semantic sample timestamp is outside the video")
            if frame.frame_index in seen_indices:
                raise ValueError("Duplicate semantic sample frame index")
            seen_indices.add(frame.frame_index)
            if frame.embedding is None:
                raise ValueError("Semantic segmentation requires SigLIP embeddings")
            if dimension is None:
                dimension = len(frame.embedding)
            frame.embedding = normalize_vectors([frame.embedding], dimension=dimension)[0]
            if span:
                previous = span[-1]
                if frame.timestamp_ms <= previous.timestamp_ms:
                    raise ValueError("Semantic samples must have strictly increasing timestamps")
                if _has_gap(previous, frame, gap_ms):
                    yield from finish(frame.timestamp_ms)
                    sequence = previous.metadata.get("sample_sequence")
                    next_sequence = frame.metadata.get("sample_sequence")
                    reason = (
                        "privacy_gap"
                        if (
                            sequence is not None
                            and next_sequence is not None
                            and next_sequence != sequence + 1
                        )
                        else "recording_gap"
                    )
                    if diagnostics is not None:
                        diagnostics[f"{reason}_count"] = diagnostics.get(f"{reason}_count", 0) + 1
                    span.clear()
            span.append(frame)
        if span:
            yield from finish()
    finally:
        if hasattr(source, "close"):
            source.close()
