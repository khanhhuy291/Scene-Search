"""Typed MinIO object-storage wrapper."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from loguru import logger
from minio import Minio
from minio.error import MinioException, S3Error
from minio.helpers import ObjectWriteResult

from core.config import MinIOSettings, get_settings


class MinIOError(RuntimeError):
    """Raised when an object-storage operation fails."""


class MinIOStorage:
    """Small, application-specific wrapper around the synchronous MinIO SDK."""

    def __init__(self, settings: MinIOSettings | None = None) -> None:
        self.settings = settings or get_settings().minio
        self.bucket = self.settings.bucket
        self.client = Minio(
            endpoint=self.settings.endpoint,
            access_key=self.settings.access_key.get_secret_value(),
            secret_key=self.settings.secret_key.get_secret_value(),
            secure=self.settings.secure,
            region=self.settings.region,
        )

    def ensure_bucket(self) -> None:
        """Create the configured bucket when it does not exist."""

        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket, location=self.settings.region)
                logger.info("Created MinIO bucket {bucket}", bucket=self.bucket)
        except S3Error as exc:
            # Another process may create the bucket between the exists check
            # and make_bucket call.
            if exc.code in {"BucketAlreadyExists", "BucketAlreadyOwnedByYou"}:
                return
            raise MinIOError(f"Unable to ensure MinIO bucket {self.bucket!r}") from exc
        except (MinioException, OSError) as exc:
            raise MinIOError(f"Unable to ensure MinIO bucket {self.bucket!r}") from exc

    def upload_file(
        self,
        object_name: str,
        file_path: str | Path,
        *,
        content_type: str = "application/octet-stream",
    ) -> ObjectWriteResult:
        """Upload a local file and return MinIO's write result."""

        source = Path(file_path)
        if not object_name.strip():
            raise ValueError("object_name cannot be empty")
        if not source.is_file():
            raise FileNotFoundError(f"Upload source is not a file: {source}")
        try:
            self.ensure_bucket()
            return self.client.fput_object(
                self.bucket,
                object_name,
                str(source),
                content_type=content_type,
            )
        except (MinioException, OSError) as exc:
            raise MinIOError(f"Unable to upload {source} as {object_name!r}") from exc

    def download_file(self, object_name: str, destination: str | Path) -> Path:
        """Download an object to ``destination`` and return its resolved path."""

        if not object_name.strip():
            raise ValueError("object_name cannot be empty")
        target = Path(destination)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            self.client.fget_object(self.bucket, object_name, str(target))
            return target.resolve()
        except (MinioException, OSError) as exc:
            raise MinIOError(f"Unable to download object {object_name!r} to {target}") from exc

    def get_presigned_url(
        self,
        object_name: str,
        *,
        expires: timedelta = timedelta(hours=1),
    ) -> str:
        """Generate a temporary GET URL for an object (maximum seven days)."""

        if not object_name.strip():
            raise ValueError("object_name cannot be empty")
        if not timedelta(seconds=1) <= expires <= timedelta(days=7):
            raise ValueError("expires must be between one second and seven days")
        try:
            return self.client.presigned_get_object(self.bucket, object_name, expires=expires)
        except (MinioException, OSError, ValueError) as exc:
            raise MinIOError(f"Unable to create a URL for object {object_name!r}") from exc


_storage: MinIOStorage | None = None


def get_minio_storage() -> MinIOStorage:
    """Return the process-wide MinIO storage wrapper."""

    global _storage
    if _storage is None:
        _storage = MinIOStorage()
    return _storage


__all__ = ["MinIOError", "MinIOStorage", "get_minio_storage"]
