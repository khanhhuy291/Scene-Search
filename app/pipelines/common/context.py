"""Runtime context shared by ingestion stages without entering Celery payloads."""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from core.config import Settings


@dataclass
class PipelineContext:
    job_id: str
    video_id: str
    raw_minio_key: str
    embedding_model: str
    settings: Settings
    source_checksum: str | None = field(default=None, kw_only=True)
    temp_dir: Path | None = None
    metrics: dict[str, int | float] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    _temporary_directory: TemporaryDirectory[str] | None = field(default=None, repr=False)

    def open_temp_dir(self) -> Path:
        if self.temp_dir is None:
            root = Path("/tmp/scenesearch")
            root.mkdir(parents=True, exist_ok=True)
            self._temporary_directory = TemporaryDirectory(prefix=f"{self.job_id}-", dir=root)
            self.temp_dir = Path(self._temporary_directory.name)
        return self.temp_dir

    def close(self) -> None:
        if self._temporary_directory is not None:
            self._temporary_directory.cleanup()
            self._temporary_directory = None

    @contextmanager
    def measure(self, stage: str):
        started = time.perf_counter()
        try:
            yield
        finally:
            key = f"{stage}_duration_ms"
            self.metrics[key] = self.metrics.get(key, 0) + (time.perf_counter() - started) * 1000

    def timed_frames(self, frames, stage: str):
        """Measure lazy iterator work, subtracting time spent in nested iterators."""
        source = iter(frames)
        key = f"{stage}_duration_ms"
        try:
            while True:
                child_start = self.state.get("iterator_duration_ms", 0)
                started = time.perf_counter()
                try:
                    frame = next(source)
                except StopIteration:
                    return
                finally:
                    elapsed = max(
                        0.0,
                        (time.perf_counter() - started) * 1000
                        - (self.state.get("iterator_duration_ms", 0) - child_start),
                    )
                    self.metrics[key] = self.metrics.get(key, 0) + elapsed
                    self.state["iterator_duration_ms"] = (
                        self.state.get("iterator_duration_ms", 0) + elapsed
                    )
                self.metrics[f"{stage}_frames"] = self.metrics.get(f"{stage}_frames", 0) + 1
                yield frame
        finally:
            if hasattr(source, "close"):
                source.close()

    def __enter__(self) -> PipelineContext:
        self.open_temp_dir()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


__all__ = ["PipelineContext"]
