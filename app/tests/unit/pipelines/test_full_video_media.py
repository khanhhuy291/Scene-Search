from types import SimpleNamespace

import av
import pytest
from PIL import Image

from core.config import Settings
from pipelines.common.context import PipelineContext
from pipelines.common.errors import RetryablePersistenceError
from pipelines.common.types import FrameRecord, SceneRecord
from pipelines.ingestion.preview_generator import generate_previews


def make_video(path):
    with av.open(str(path), "w") as output:
        stream = output.add_stream("libx264", rate=4)
        stream.width, stream.height, stream.pix_fmt = 32, 24, "yuv420p"
        for index in range(24):
            image = Image.new("RGB", (32, 24), (index * 10, 40, 80))
            frame = av.VideoFrame.from_image(image)
            image.close()
            for packet in stream.encode(frame):
                output.mux(packet)
        for packet in stream.encode():
            output.mux(packet)


@pytest.mark.asyncio
async def test_segments_share_complete_video_and_have_unique_thumbnails(tmp_path):
    source = tmp_path / "source.mov"
    make_video(source)
    objects = {}

    def upload(key, path, **kwargs):
        objects[key] = path.read_bytes()

    storage = SimpleNamespace(upload_file=upload, delete_object=lambda key: objects.pop(key, None))
    frames = [FrameRecord(i * 2000, i, Image.new("RGB", (32, 24))) for i in range(2)]
    scenes = [
        SceneRecord(f"scene-{i}", "video-1", i * 2000, i * 2000 + 1000, [f])
        for i, f in enumerate(frames)
    ]
    ctx = PipelineContext("job", "video-1", "raw.mov", "v1", "qwen", Settings(), temp_dir=tmp_path)
    try:
        uploaded = await generate_previews(ctx, scenes, storage, source)
        key = "videos/video-1/playback.mp4"
        assert uploaded == [
            key,
            "videos/video-1/segments/scene-0/thumbnail.jpg",
            "videos/video-1/segments/scene-1/thumbnail.jpg",
        ]
        assert all(scene.preview_key == key for scene in scenes)
        playback = tmp_path / "result.mp4"
        playback.write_bytes(objects[key])
        with av.open(str(playback)) as video:
            decoded = list(video.decode(video=0))
            assert len(decoded) == 24  # Includes every source frame, beyond both segments.
            assert float(decoded[-1].time) == pytest.approx(5.75)
            assert decoded[0].to_ndarray().tobytes() != decoded[-1].to_ndarray().tobytes()
    finally:
        for frame in frames:
            frame.image.close()


@pytest.mark.asyncio
async def test_invalid_source_fails_instead_of_publishing_empty_playback(tmp_path):
    ctx = PipelineContext("job", "video-1", "raw.mov", "v1", "qwen", Settings(), temp_dir=tmp_path)
    uploaded = []
    storage = SimpleNamespace(upload_file=lambda *args, **kwargs: uploaded.append(args))
    with pytest.raises(RetryablePersistenceError):
        await generate_previews(ctx, [], storage, tmp_path / "missing.mov")
    assert uploaded == []
