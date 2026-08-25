"""Face and plate anonymization for displayed assets (ADR-0003).

Region detection sits behind an interface with two implementations. The default
derives regions from corpus ground-truth boxes, which costs no model download
and no inference pass; a real face/plate detector drops into the same interface
later without touching the pipeline.

The heuristic deliberately over-blurs. It blurs heads that are turned away and
vehicle regions with no visible plate. Over-blurring is the correct direction to
fail in, and the measured leak rate is reported rather than a claim of
perfection being made.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - typing only
    from PIL.Image import Image

# Corpus categories whose boxes imply a face, and those that imply a plate.
PERSON_CLASSES = frozenset({"person", "pedestrian", "rider"})
VEHICLE_CLASSES = frozenset({"car", "truck", "bus", "trailer", "other vehicle", "caravan"})

# Fraction of a person box, measured from the top, assumed to contain the head.
HEAD_FRACTION = 0.40
# Fraction of a vehicle box, measured from the bottom, assumed to contain the plate.
PLATE_FRACTION = 0.35
# Horizontal inset applied to the plate region, since plates sit centrally.
PLATE_INSET = 0.20
# Regions are grown slightly, because ground-truth boxes are tight.
DILATION = 0.10
# Below this, a region is a handful of pixels and blurring it achieves nothing
# while still costing a compositing operation.
MIN_REGION_PIXELS = 6


@dataclass(frozen=True)
class BlurRegion:
    """An axis-aligned region to obscure, in pixel coordinates."""

    x1: float
    y1: float
    x2: float
    y2: float
    reason: str

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    def clamped(self, width: int, height: int) -> BlurRegion:
        return BlurRegion(
            x1=max(0.0, min(self.x1, width)),
            y1=max(0.0, min(self.y1, height)),
            x2=max(0.0, min(self.x2, width)),
            y2=max(0.0, min(self.y2, height)),
            reason=self.reason,
        )

    def is_meaningful(self) -> bool:
        return self.width >= MIN_REGION_PIXELS and self.height >= MIN_REGION_PIXELS


@runtime_checkable
class BlurRegionDetector(Protocol):
    """Produces the regions of a frame that must be obscured."""

    def detect(
        self, image: Image, objects: list[dict[str, object]] | None = None
    ) -> list[BlurRegion]: ...


def _dilate(x1: float, y1: float, x2: float, y2: float, factor: float) -> tuple[float, ...]:
    dx = (x2 - x1) * factor / 2
    dy = (y2 - y1) * factor / 2
    return x1 - dx, y1 - dy, x2 + dx, y2 + dy


class LabelHeuristicDetector:
    """Derives blur regions from ground-truth object boxes.

    Prototype-grade by design (ADR-0003): it uses labels the dataset already
    provides rather than adding a model to the critical path of a two-week
    build. It is not a face detector and does not claim to be.
    """

    name = "label-heuristic-v1"

    def detect(
        self, image: Image, objects: list[dict[str, object]] | None = None
    ) -> list[BlurRegion]:
        if not objects:
            return []

        width, height = image.size
        regions: list[BlurRegion] = []

        for entry in objects:
            category = str(entry.get("category", "")).lower()
            box = entry.get("box2d")
            if not isinstance(box, list | tuple) or len(box) != 4:
                continue
            try:
                x1, y1, x2, y2 = (float(value) for value in box)
            except (TypeError, ValueError):
                continue
            if x2 <= x1 or y2 <= y1:
                continue

            if category in PERSON_CLASSES:
                head_bottom = y1 + (y2 - y1) * HEAD_FRACTION
                coords = _dilate(x1, y1, x2, head_bottom, DILATION)
                regions.append(BlurRegion(*coords, reason="face"))
            elif category in VEHICLE_CLASSES:
                plate_top = y2 - (y2 - y1) * PLATE_FRACTION
                inset = (x2 - x1) * PLATE_INSET
                coords = _dilate(x1 + inset, plate_top, x2 - inset, y2, DILATION)
                regions.append(BlurRegion(*coords, reason="plate"))

        return [
            clamped
            for clamped in (region.clamped(width, height) for region in regions)
            if clamped.is_meaningful()
        ]


class NullDetector:
    """Finds nothing. Used only to measure the leak rate of an unblurred frame."""

    name = "null"

    def detect(
        self, image: Image, objects: list[dict[str, object]] | None = None
    ) -> list[BlurRegion]:
        return []


class FullFrameDetector:
    """Blur the entire frame when no trusted region metadata is available.

    This is the fail-closed fallback for arbitrary direct uploads. It sacrifices
    thumbnail utility rather than pretending an unlabeled frame was anonymized.
    """

    name = "full-frame-fallback-v1"

    def detect(
        self, image: Image, objects: list[dict[str, object]] | None = None
    ) -> list[BlurRegion]:
        width, height = image.size
        return [BlurRegion(0.0, 0.0, float(width), float(height), reason="privacy-fallback")]


def apply_blur(image: Image, regions: list[BlurRegion]) -> Image:
    """Return a copy of ``image`` with each region Gaussian-blurred.

    The blur radius scales with region size. A fixed radius would leave a large
    nearby face recognizable while destroying a distant one unnecessarily.
    """

    from PIL import ImageFilter

    if not regions:
        return image.copy()

    output = image.copy()
    for region in regions:
        box = (
            int(region.x1),
            int(region.y1),
            int(max(region.x1 + 1, region.x2)),
            int(max(region.y1 + 1, region.y2)),
        )
        patch = output.crop(box)
        radius = max(2.0, min(region.width, region.height) / 3.0)
        output.paste(patch.filter(ImageFilter.GaussianBlur(radius=radius)), box)
    return output


@dataclass
class AnonymizationResult:
    """Outcome of anonymizing one frame."""

    image: Image
    region_count: int
    # False only when anonymization could not be completed. Callers must treat
    # a false value as "do not display" rather than "no regions found"
    # (ADR-0003, fail closed).
    blurred: bool = True
    error: str | None = None


def anonymize_frame(
    image: Image,
    objects: list[dict[str, object]] | None = None,
    detector: BlurRegionDetector | None = None,
) -> AnonymizationResult:
    """Blur a frame, failing closed.

    A frame with no detected regions is still ``blurred=True``: the pass ran and
    found nothing. Only an exception produces ``blurred=False``, which excludes
    the frame from every display path. The distinction matters -- conflating
    "nothing to blur" with "blurring failed" would either hide clean frames or,
    far worse, show unprocessed ones.
    """

    detector = detector or LabelHeuristicDetector()
    try:
        regions = detector.detect(image, objects)
        return AnonymizationResult(
            image=apply_blur(image, regions), region_count=len(regions), blurred=True
        )
    except Exception as exc:  # noqa: BLE001 - any failure must fail closed
        return AnonymizationResult(image=image, region_count=0, blurred=False, error=str(exc))


__all__ = [
    "AnonymizationResult",
    "BlurRegion",
    "BlurRegionDetector",
    "FullFrameDetector",
    "LabelHeuristicDetector",
    "NullDetector",
    "PERSON_CLASSES",
    "VEHICLE_CLASSES",
    "anonymize_frame",
    "apply_blur",
]
