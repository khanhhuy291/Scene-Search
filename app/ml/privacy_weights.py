"""Resolve the configured YOLO checkpoint before ingestion."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING

import httpx
from filelock import FileLock

if TYPE_CHECKING:
    from core.config import MLSettings


def resolve_privacy_weights(settings: MLSettings) -> Path:
    if settings.privacy_yolo_weights is not None:
        weights = settings.privacy_yolo_weights.expanduser()
        if not weights.is_file():
            raise ValueError("ML_PRIVACY_YOLO_WEIGHTS must point to an existing checkpoint")
        return weights

    url = settings.privacy_yolo_weights_url
    digest = settings.privacy_yolo_weights_sha256
    if url is None or digest is None:
        raise ValueError(
            "Set ML_PRIVACY_YOLO_WEIGHTS or both ML_PRIVACY_YOLO_WEIGHTS_URL "
            "and ML_PRIVACY_YOLO_WEIGHTS_SHA256"
        )
    if url.scheme != "https":
        raise ValueError("ML_PRIVACY_YOLO_WEIGHTS_URL must use HTTPS")
    return _resolve_download(str(url), digest.lower(), settings.privacy_yolo_cache_dir.expanduser())


@lru_cache(maxsize=1)
def _resolve_download(url: str, digest: str, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"privacy-{digest}.pt"
    with FileLock(str(target) + ".lock", timeout=300):
        if target.is_file():
            with target.open("rb") as cached:
                if hashlib.file_digest(cached, "sha256").hexdigest() == digest:
                    return target

        temporary = None
        try:
            with NamedTemporaryFile(dir=cache_dir, suffix=".part", delete=False) as output:
                temporary = Path(output.name)
                checksum = hashlib.sha256()
                with httpx.stream("GET", url, follow_redirects=True, timeout=30.0) as response:
                    response.raise_for_status()
                    for chunk in response.iter_bytes():
                        output.write(chunk)
                        checksum.update(chunk)
            if checksum.hexdigest() != digest:
                raise ValueError("Downloaded YOLO checkpoint failed SHA-256 verification")
            temporary.replace(target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return target
