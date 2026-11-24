"""Deterministic, privacy-safe VLM selection before image disposal."""

from core.config import VideoSettings
from pipelines.common.types import FrameRecord, SceneRecord
from pipelines.ingestion.deduplicator import cosine


def select_vlm_candidates(
    scene: SceneRecord, samples: list[FrameRecord], settings: VideoSettings
) -> None:
    representative = scene.representative_frame
    if representative is None:
        raise ValueError("VLM selection requires a representative frame")
    selected = [representative]
    remaining = [
        frame
        for frame in samples
        if frame.frame_index != representative.frame_index
        and frame.privacy_status == "verified"
        and frame.display_image is not None
    ]
    while len(selected) < settings.vlm_max_frames and remaining:
        if any(frame.embedding is None for frame in selected + remaining):
            raise ValueError("VLM novelty selection requires SigLIP embeddings")

        def score(frame: FrameRecord) -> tuple[float, int, int, int]:
            return (
                min(1 - cosine(frame.embedding, other.embedding) for other in selected),
                min(abs(frame.timestamp_ms - other.timestamp_ms) for other in selected),
                -frame.timestamp_ms,
                -frame.frame_index,
            )

        chosen = max(remaining, key=score)
        if score(chosen)[0] <= settings.vlm_novelty_distance:
            break
        selected.append(chosen)
        remaining = [f for f in remaining if f.frame_index != chosen.frame_index]
    scene.vlm_candidates = selected
