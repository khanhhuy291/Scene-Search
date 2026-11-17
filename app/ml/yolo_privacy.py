"""YOLO face and plate detection for derivative images."""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from ml.anonymize import BlurRegion

if TYPE_CHECKING:
    from PIL.Image import Image

_REASONS = {"face": "face", "license_plate": "plate"}
_REGION_PADDING = 0.20


class YOLOPrivacyDetector:
    def __init__(self, weights: Path, *, confidence: float, image_size: int) -> None:
        if not weights.is_file():
            raise ValueError("ML_PRIVACY_YOLO_WEIGHTS must point to a local checkpoint")

        from ultralytics import YOLO

        self._model = YOLO(str(weights), task="detect")
        self._labels = {
            index: name.strip().lower().replace("-", "_").replace(" ", "_")
            for index, name in self._model.names.items()
        }
        if not _REASONS.keys() <= set(self._labels.values()):
            raise ValueError("Privacy checkpoint must detect face and license_plate")
        self._confidence = confidence
        self._image_size = image_size

    def detect(
        self, image: Image, objects: list[dict[str, object]] | None = None
    ) -> list[BlurRegion]:
        (result,) = self._model.predict(
            image, conf=self._confidence, imgsz=self._image_size, verbose=False
        )
        if result.boxes is None:
            raise ValueError("Privacy inference did not return detection boxes")

        regions = []
        for box, class_id in zip(
            result.boxes.xyxy.tolist(), result.boxes.cls.tolist(), strict=True
        ):
            reason = _REASONS.get(self._labels[int(class_id)])
            if reason is None:
                continue
            x1, y1, x2, y2 = box
            if not all(math.isfinite(value) for value in box) or x2 <= x1 or y2 <= y1:
                raise ValueError("Privacy inference returned an invalid bounding box")
            dx = (x2 - x1) * _REGION_PADDING / 2
            dy = (y2 - y1) * _REGION_PADDING / 2
            region = BlurRegion(x1 - dx, y1 - dy, x2 + dx, y2 + dy, reason)
            region = region.clamped(*image.size)
            if region.width <= 0 or region.height <= 0:
                raise ValueError("Privacy bounding box falls outside the image")
            regions.append(
                BlurRegion(
                    math.floor(region.x1),
                    math.floor(region.y1),
                    math.ceil(region.x2),
                    math.ceil(region.y2),
                    reason,
                )
            )
        return regions


@lru_cache(maxsize=1)
def get_yolo_privacy_detector(
    weights: Path, confidence: float, image_size: int
) -> YOLOPrivacyDetector:
    return YOLOPrivacyDetector(weights, confidence=confidence, image_size=image_size)
