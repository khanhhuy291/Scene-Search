"""Job-local, lossless image storage for embedding-only scene construction."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from pipelines.common.types import FrameRecord


class FrameStore:
    """Keep shared frame records and vectors, loading pixels only for the active chunk."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.frames: dict[int, FrameRecord] = {}

    def stage(self, frame: FrameRecord) -> None:
        if frame.frame_index in self.frames:
            raise ValueError("Duplicate staged frame index")
        if frame.privacy_status != "verified" or frame.display_image is None:
            raise ValueError("Frame storage requires a verified privacy derivative")
        self.frames[frame.frame_index] = frame
        try:
            frame.image.save(self.root / f"{frame.frame_index}-source.png", format="PNG")
            frame.display_image.save(self.root / f"{frame.frame_index}-display.png", format="PNG")
        finally:
            frame.close()

    def load(self, frames: list[FrameRecord]) -> None:
        try:
            for frame in frames:
                if self.frames.get(frame.frame_index) is not frame:
                    raise ValueError("Unknown staged frame reference")
                with Image.open(self.root / f"{frame.frame_index}-source.png") as source:
                    frame.image = source.copy()
                with Image.open(self.root / f"{frame.frame_index}-display.png") as display:
                    frame.display_image = display.copy()
        except Exception:
            for frame in frames:
                frame.close()
            raise

    def close(self) -> None:
        for frame in self.frames.values():
            frame.close()
            frame.embedding = frame.qwen_embedding = None
