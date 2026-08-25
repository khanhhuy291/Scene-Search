"""Runtime context shared by ingestion stages without entering Celery payloads."""

from __future__ import annotations

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
    pipeline_version: str
    embedding_model: str
    settings: Settings
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

    def __enter__(self) -> PipelineContext:
        self.open_temp_dir()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


__all__ = ["PipelineContext"]
