"""Application-wide structured logging configuration."""

from __future__ import annotations

import logging
import sys
from types import FrameType
from typing import cast

from loguru import logger


class InterceptHandler(logging.Handler):
    """Forward standard-library log records to Loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame: FrameType | None = logging.currentframe()
        depth = 2
        while frame is not None and (
            frame.f_code.co_filename == logging.__file__ or frame.f_code.co_filename == __file__
        ):
            frame = cast(FrameType | None, frame.f_back)
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def configure_logging(
    level: str = "INFO",
    *,
    json_logs: bool = True,
    intercept_loggers: tuple[str, ...] = (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "sqlalchemy.engine",
        "celery",
        "celery.task",
        "celery.worker",
    ),
) -> None:
    """Configure Loguru and route Python logging through it.

    Calling this function repeatedly is safe; existing Loguru sinks and root
    logging handlers are replaced rather than duplicated.
    """

    normalized_level = level.upper()
    try:
        logger.level(normalized_level)
    except ValueError as exc:
        raise ValueError(f"Unknown log level: {level!r}") from exc

    logger.remove()
    logger.add(
        sys.stderr,
        level=normalized_level,
        serialize=json_logs,
        backtrace=False,
        diagnose=False,
        enqueue=False,
    )

    handler = InterceptHandler()
    logging.basicConfig(handlers=[handler], level=0, force=True)
    for logger_name in intercept_loggers:
        stdlib_logger = logging.getLogger(logger_name)
        stdlib_logger.handlers = [handler]
        stdlib_logger.propagate = False
        stdlib_logger.setLevel(0)


__all__ = ["InterceptHandler", "configure_logging", "logger"]
