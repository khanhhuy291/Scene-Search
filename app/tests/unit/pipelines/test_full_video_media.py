from fractions import Fraction
from io import BytesIO
from types import SimpleNamespace

import av
import pytest
from PIL import Image, ImageStat

from core.config import Settings
from ml.anonymize import FullFrameDetector
from pipelines.common.context import PipelineContext
from pipelines.common.errors import RetryablePersistenceError
from pipelines.common.types import FrameRecord, SceneRecord
from pipelines.ingestion.preview_generator import generate_previews

TIMESTAMPS_MS = [0, 121, 370, 721]


@pytest.fixture
def source_video(tmp_path):
    source = tmp_path / "input.mp4"
    time_base = Fraction(1, 1000)
    with av.open(str(source), "w") as container:
        video = container.add_stream("libx264", rate=5)
        video.width = video.height = 48
        video.pix_fmt = "yuv420p"
        video.codec_context.time_base = time_base
        audio = container.add_stream("aac", rate=48000)

        for timestamp in TIMESTAMPS_MS:
            with Image.new("RGB", (48, 48), "white") as image:
                image.paste("black", (0, 0, 24, 48))
                frame = av.VideoFrame.from_image(image)
            frame.pts = timestamp
            frame.time_base = time_base
            container.mux(video.encode(frame))
        container.mux(video.encode())

        samples = av.AudioFrame(format="fltp", layout="stereo", samples=1024)
        samples.sample_rate = 48000
        for plane in samples.planes:
            plane.update(bytes(plane.buffer_size))
        container.mux(audio.encode(samples))
        container.mux(audio.encode())
    return source


@pytest.mark.asyncio
async def test_publishes_anonymized_playback_and_verified_thumbnail(tmp_path, source_video):
    objects = {}

    def upload(key, path, **kwargs):
        objects[key] = path.read_bytes()

    storage = SimpleNamespace(upload_file=upload, delete_object=objects.pop)
    ctx = PipelineContext("job", "video-1", "raw.mp4", "v1", "qwen", Settings(), temp_dir=tmp_path)
    with (
        Image.new("RGB", (32, 24), "red") as original,
        Image.new("RGB", (32, 24), "black") as derivative,
    ):
        frame = FrameRecord(0, 0, original, privacy_status="verified", display_image=derivative)
        scene = SceneRecord("scene-1", "video-1", 0, 1000, [frame])
        uploaded = await generate_previews(
            ctx, [scene], storage, source_video=source_video, detector=FullFrameDetector()
        )

    playback_key = "videos/video-1/playback-yolo-v1/job.mp4"
    thumbnail_key = "videos/video-1/segments/scene-1/thumbnail-yolo-v1/job.jpg"
    assert uploaded == [playback_key, thumbnail_key]
    assert scene.preview_key == playback_key
    with Image.open(BytesIO(objects[thumbnail_key])) as image:
        assert image.getpixel((0, 0)) == (0, 0, 0)

    with (
        av.open(str(source_video)) as source,
        av.open(BytesIO(objects[playback_key])) as playback,
    ):
        assert source.streams.audio
        assert not playback.streams.audio
        assert playback.streams.video[0].codec_context.name == "h264"
        frames = list(playback.decode(video=0))
        assert [round(frame.time * 1000) for frame in frames] == TIMESTAMPS_MS
        for original_frame, redacted_frame in zip(source.decode(video=0), frames, strict=True):
            with original_frame.to_image() as original, redacted_frame.to_image() as redacted:
                assert ImageStat.Stat(redacted).stddev[0] < ImageStat.Stat(original).stddev[0] * 0.8


@pytest.mark.asyncio
async def test_anonymization_error_after_first_frame_prevents_upload(tmp_path, source_video):
    class FailingDetector(FullFrameDetector):
        calls = 0

        def detect(self, image, objects=None):
            self.calls += 1
            if self.calls == 2:
                raise ValueError("detector failed")
            return super().detect(image, objects)

    ctx = PipelineContext("job", "video-1", "raw.mp4", "v1", "qwen", Settings(), temp_dir=tmp_path)
    uploaded = []
    storage = SimpleNamespace(upload_file=lambda *args, **kwargs: uploaded.append(args))
    detector = FailingDetector()
    with pytest.raises(RetryablePersistenceError) as error:
        await generate_previews(ctx, [], storage, source_video=source_video, detector=detector)
    assert "frame 1" in str(error.value.__cause__)
    assert uploaded == []
