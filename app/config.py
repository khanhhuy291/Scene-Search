"""Backward-compatible imports for the settings module.

New code should import from :mod:`core.config`.
"""

from core.config import Settings, get_settings

__all__ = ["Settings", "get_settings"]
