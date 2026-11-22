"""Object keys published by the YOLO anonymization pipeline."""

import re
from typing import TypeGuard

THUMBNAIL_VERSION = "yolo-v1"
PLAYBACK_VERSION = "yolo-v1"
_THUMBNAIL_KEY = re.compile(
    rf"videos/[a-zA-Z0-9_-]+/segments/[a-zA-Z0-9_-]+/thumbnail-{THUMBNAIL_VERSION}/"
    r"[a-zA-Z0-9_-]+\.jpg"
)


_PLAYBACK_KEY = re.compile(
    rf"videos/[a-zA-Z0-9_-]+/playback-{PLAYBACK_VERSION}/[a-zA-Z0-9_-]+\.mp4"
)


def is_anonymized_playback(key: object) -> TypeGuard[str]:
    return isinstance(key, str) and _PLAYBACK_KEY.fullmatch(key) is not None


def is_anonymized_thumbnail(key: object) -> TypeGuard[str]:
    return isinstance(key, str) and _THUMBNAIL_KEY.fullmatch(key) is not None
