"""Stable error taxonomy for ingestion operations."""


class PipelineError(RuntimeError):
    """Base class carrying a machine-readable code and stage."""

    code = "pipeline_error"

    def __init__(self, message: str, *, stage: str = "unknown") -> None:
        super().__init__(message)
        self.stage = stage


class RetryablePipelineError(PipelineError):
    """A transient infrastructure failure that Celery may safely retry."""


class PermanentPipelineError(PipelineError):
    """Invalid input or configuration that retrying cannot repair."""


class VideoAcquireError(PermanentPipelineError):
    code = "video_acquire_error"


class RetryableVideoAcquireError(RetryablePipelineError):
    code = "video_acquire_error"


class VideoDecodeError(PermanentPipelineError):
    code = "video_decode_error"


class VideoValidationError(PermanentPipelineError):
    code = "video_validation_error"


class PrivacyVerificationError(PermanentPipelineError):
    code = "privacy_verification_error"


class EmbeddingError(PermanentPipelineError):
    code = "embedding_error"


class IngestionCancelledError(PermanentPipelineError):
    code = "ingestion_cancelled"


class PersistenceError(PermanentPipelineError):
    code = "persistence_error"


class RetryablePersistenceError(RetryablePipelineError):
    code = "persistence_error"


__all__ = [
    "EmbeddingError",
    "IngestionCancelledError",
    "PermanentPipelineError",
    "PersistenceError",
    "PipelineError",
    "PrivacyVerificationError",
    "RetryablePersistenceError",
    "RetryablePipelineError",
    "RetryableVideoAcquireError",
    "VideoAcquireError",
    "VideoDecodeError",
    "VideoValidationError",
]
