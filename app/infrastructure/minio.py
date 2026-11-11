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


class RestrictedObjectError(MinIOError):
    """Raised on an attempt to issue a URL for a restricted original."""


class MinIOStorage:
    """Small, application-specific wrapper around the synchronous MinIO SDK.

    A store is either **servable** or **restricted** (ADR-0003). Restricted
    stores hold original frames and clips and refuse to produce a presigned URL
    at all, so "never serve an original" is enforced by the type of the store an
    object lives in rather than by every call site remembering to check.
    """

    def __init__(
        self,
        settings: MinIOSettings | None = None,
        *,
        bucket: str | None = None,
        servable: bool = True,
    ) -> None:
        self.settings = settings or get_settings().minio
        self.bucket = bucket or self.settings.bucket
        self.servable = servable
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

    def read_object(self, object_name: str) -> bytes:
        """Read one object into memory and always release the MinIO response."""

        if not object_name.strip():
            raise ValueError("object_name cannot be empty")
        response = None
        try:
            response = self.client.get_object(self.bucket, object_name)
            return response.read()
        except (MinioException, OSError) as exc:
            raise MinIOError(f"Unable to read object {object_name!r}") from exc
        finally:
            if response is not None:
                response.close()
                response.release_conn()

    def delete_object(self, object_name: str) -> None:
        """Delete an object during compensating cleanup."""

        if not object_name.strip():
            raise ValueError("object_name cannot be empty")
        try:
            self.client.remove_object(self.bucket, object_name)
        except (MinioException, OSError) as exc:
            raise MinIOError(f"Unable to delete object {object_name!r}") from exc

    def delete_prefix(self, prefix: str) -> int:
        """Delete every object below a deterministic video prefix."""
        normalized = prefix.strip().lstrip("/")
        if not normalized or not normalized.endswith("/"):
            raise ValueError("prefix must be a non-empty directory prefix ending in '/'")
        deleted = 0
        try:
            for item in self.client.list_objects(self.bucket, prefix=normalized, recursive=True):
                self.client.remove_object(self.bucket, item.object_name)
                deleted += 1
        except (MinioException, OSError) as exc:
            raise MinIOError(
                f"Unable to delete objects below {normalized!r} from {self.bucket!r}"
            ) from exc
        return deleted

    def get_presigned_url(
        self,
        object_name: str,
        *,
        expires: timedelta | None = None,
    ) -> str:
        """Generate a temporary GET URL for an object (maximum seven days).

        Refuses outright on a restricted store. This is the enforcement point
        for "no original is ever served" (ADR-0003).
        """

        if not self.servable:
            raise RestrictedObjectError(
                f"Bucket {self.bucket!r} holds restricted originals and cannot be "
                "presigned. Serve the anonymized derivative instead."
            )
        if not object_name.strip():
            raise ValueError("object_name cannot be empty")
        if expires is None:
            expires = timedelta(seconds=self.settings.url_ttl_seconds)
        if not timedelta(seconds=1) <= expires <= timedelta(days=7):
            raise ValueError("expires must be between one second and seven days")
        try:
            return self.client.presigned_get_object(self.bucket, object_name, expires=expires)
        except (MinioException, OSError, ValueError) as exc:
            raise MinIOError(f"Unable to create a URL for object {object_name!r}") from exc

    def get_presigned_upload_url(
        self,
        object_name: str,
        *,
        expires: timedelta | None = None,
    ) -> str:
        """Generate a temporary PUT upload URL for direct client-to-storage uploads."""
        if not object_name.strip():
            raise ValueError("object_name cannot be empty")
        if expires is None:
            expires = timedelta(seconds=self.settings.url_ttl_seconds)
        if not timedelta(seconds=1) <= expires <= timedelta(days=7):
            raise ValueError("expires must be between one second and seven days")
        try:
            self.ensure_bucket()
            return self.client.presigned_put_object(self.bucket, object_name, expires=expires)
        except (MinioException, OSError, ValueError) as exc:
            raise MinIOError(f"Unable to create upload URL for object {object_name!r}") from exc


_storage: MinIOStorage | None = None
_raw_storage: MinIOStorage | None = None
_derived_storage: MinIOStorage | None = None


def get_minio_storage() -> MinIOStorage:
    """Return the process-wide MinIO storage wrapper for the default bucket."""

    global _storage
    if _storage is None:
        _storage = MinIOStorage()
    return _storage


def get_raw_storage() -> MinIOStorage:
    """Return the restricted store holding original frames and clips.

    Objects here are never presigned; the store raises rather than signing.
    """

    global _raw_storage
    if _raw_storage is None:
        settings = get_settings().minio
        _raw_storage = MinIOStorage(settings, bucket=settings.raw_bucket, servable=False)
    return _raw_storage


def get_derived_storage() -> MinIOStorage:
    """Return the servable store holding anonymized thumbnails and previews."""

    global _derived_storage
    if _derived_storage is None:
        settings = get_settings().minio
        _derived_storage = MinIOStorage(settings, bucket=settings.derived_bucket, servable=True)
    return _derived_storage


def reset_storage_cache() -> None:
    """Drop cached stores so settings changes take effect (used by tests)."""

    global _storage, _raw_storage, _derived_storage
    _storage = _raw_storage = _derived_storage = None


__all__ = [
    "MinIOError",
    "MinIOStorage",
    "RestrictedObjectError",
    "get_derived_storage",
    "get_minio_storage",
    "get_raw_storage",
    "reset_storage_cache",
]
