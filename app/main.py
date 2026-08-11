"""Compatibility entry point for ``uvicorn main:app``."""

from api.main import app

__all__ = ["app"]
