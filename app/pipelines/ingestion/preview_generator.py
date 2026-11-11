"""One full-motion playback per video and one thumbnail per segment.

Playback preserves the source imagery; it is not an anonymized reconstruction.
Segment start/end timestamps stay relative to the complete source timeline.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from fractions import Fraction
from pathlib import Path

from infrastructure.minio import MinIOStorage
from pipelines.common.context import PipelineContext
from pipelines.common.errors import RetryablePersistenceError
from pipelines.common.types import SceneRecord
from pipelines.ingestion.video_reader import apply_display_rotation, display_rotation_ccw


def _preview_size(width: int, height: int, max_edge: int) -> tuple[int, int]:
    scale = min(1.0, max_edge / max(width, height))
    return max(2, int(width * scale) // 2 * 2), max(2, int(height * scale) // 2 * 2)


def _write_full_video(source: Path, destination: Path, ctx: PipelineContext) -> None:
    import av

    with av.open(str(source)) as incoming:
        video = incoming.streams.video[0]
        if video.codec_context.name == "h264":
            # BDD100K MOV is H.264. Remux every packet without sampling/re-encoding.
            streams = [video, *[s for s in incoming.streams.audio if s.codec_context.name == "aac"]]
            with av.open(str(destination), "w", options={"movflags": "+faststart"}) as output:
                mapping = {s.index: output.add_stream_from_template(s) for s in streams}
                for packet in incoming.demux(streams):
                    if packet.dts is None:
                        continue
                    packet.stream = mapping[packet.stream.index]
                    output.mux(packet)
        else:
            # Unsupported browser codecs are transcoded at source cadence, never
            # from the sparsely sampled frames used for retrieval.
            rate = video.average_rate or video.guessed_rate or Fraction(30, 1)
            clock = Fraction(1, 90000)
            with av.open(str(destination), "w", options={"movflags": "+faststart"}) as output:
                stream = output.add_stream("libx264", rate=rate)
                stream.pix_fmt = "yuv420p"
                stream.options = {"crf": str(ctx.settings.video.preview_crf), "preset": "veryfast"}
                for index, frame in enumerate(incoming.decode(video=0)):
                    image = apply_display_rotation(
                        frame.to_image(), display_rotation_ccw(frame, video)
                    )
                    try:
                        width, height = _preview_size(
                            *image.size, ctx.settings.video.preview_max_edge
                        )
                        stream.width, stream.height = width, height
                        resized = image.resize((width, height))
                        try:
                            encoded_frame = av.VideoFrame.from_image(resized)
                        finally:
                            resized.close()
                    finally:
                        image.close()
                    timestamp = float(frame.time) if frame.time is not None else index / float(rate)
                    encoded_frame.pts = round(timestamp / float(clock))
                    encoded_frame.time_base = clock
                    for packet in stream.encode(encoded_frame):
                        output.mux(packet)
                for packet in stream.encode():
                    output.mux(packet)
    if not destination.is_file() or destination.stat().st_size == 0:
        raise ValueError("Full-video playback is empty")


async def generate_previews(
    ctx: PipelineContext,
    scenes: list[SceneRecord],
    derived_storage: MinIOStorage,
    source_video: Path,
) -> list[str]:
    uploaded: list[str] = []
    root = ctx.open_temp_dir() / "media"
    root.mkdir(parents=True, exist_ok=True)
    playback_key = f"videos/{ctx.video_id}/playback.mp4"
    playback_path = root / "playback.mp4"
    try:
        await asyncio.to_thread(_write_full_video, source_video, playback_path, ctx)
        await asyncio.to_thread(
            derived_storage.upload_file, playback_key, playback_path, content_type="video/mp4"
        )
        uploaded.append(playback_key)
        for scene in scenes:
            thumbnail_key = f"videos/{ctx.video_id}/segments/{scene.scene_id}/thumbnail.jpg"
            thumbnail_path = root / f"{scene.scene_id}.jpg"
            thumbnail = scene.keyframes[len(scene.keyframes) // 2].image.convert("RGB")
            try:
                thumbnail.thumbnail((ctx.settings.dataset.thumbnail_max_edge,) * 2)
                thumbnail.save(
                    thumbnail_path, format="JPEG", quality=ctx.settings.dataset.thumbnail_quality
                )
            finally:
                thumbnail.close()
            await asyncio.to_thread(
                derived_storage.upload_file,
                thumbnail_key,
                thumbnail_path,
                content_type="image/jpeg",
            )
            uploaded.append(thumbnail_key)
            scene.thumbnail_key = thumbnail_key
            scene.preview_key = playback_key
        return uploaded
    except Exception as exc:
        for key in uploaded:
            with suppress(Exception):
                await asyncio.to_thread(derived_storage.delete_object, key)
        raise RetryablePersistenceError(
            "Unable to publish full-video media", stage="preview_generation"
        ) from exc


__all__ = ["generate_previews"]
