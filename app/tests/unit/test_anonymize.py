"""Anonymization region derivation, blurring, and fail-closed behaviour."""

from __future__ import annotations

import pytest

from ml.anonymize import (
    BlurRegion,
    FullFrameDetector,
    LabelHeuristicDetector,
    NullDetector,
    anonymize_frame,
    apply_blur,
)

pytest.importorskip("PIL", reason="Pillow is part of the ML extra")

from PIL import Image, ImageDraw  # noqa: E402


def checkered(width: int = 200, height: int = 120) -> Image.Image:
    """High-frequency content, so blurring produces a measurable change."""

    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    for x in range(0, width, 4):
        for y in range(0, height, 4):
            if (x // 4 + y // 4) % 2 == 0:
                draw.rectangle([x, y, x + 3, y + 3], fill=(0, 0, 0))
    return image


def variance(image: Image.Image, box: tuple[int, int, int, int]) -> float:
    pixels = list(image.crop(box).convert("L").tobytes())
    mean = sum(pixels) / len(pixels)
    return sum((p - mean) ** 2 for p in pixels) / len(pixels)


def test_full_frame_fallback_never_claims_an_unlabeled_frame_is_clear() -> None:
    image = checkered()
    result = anonymize_frame(image, detector=FullFrameDetector())

    assert result.blurred
    assert result.region_count == 1
    assert variance(result.image, (0, 0, *image.size)) < variance(image, (0, 0, *image.size))


def test_person_box_yields_a_head_region_near_the_top() -> None:
    detector = LabelHeuristicDetector()
    regions = detector.detect(
        checkered(), [{"category": "pedestrian", "box2d": [40.0, 20.0, 80.0, 100.0]}]
    )
    assert len(regions) == 1
    region = regions[0]
    assert region.reason == "face"
    # The head region covers the top of the box, not its full height.
    assert region.y1 < 25.0
    assert region.y2 < 60.0


def test_vehicle_box_yields_a_plate_region_near_the_bottom() -> None:
    detector = LabelHeuristicDetector()
    regions = detector.detect(
        checkered(), [{"category": "car", "box2d": [10.0, 10.0, 110.0, 90.0]}]
    )
    assert len(regions) == 1
    region = regions[0]
    assert region.reason == "plate"
    assert region.y2 > 85.0
    # Plates sit centrally, so the region is inset horizontally.
    assert region.x1 > 10.0
    assert region.x2 < 110.0


def test_unrelated_classes_produce_no_regions() -> None:
    detector = LabelHeuristicDetector()
    assert (
        detector.detect(checkered(), [{"category": "traffic light", "box2d": [0, 0, 10, 10]}]) == []
    )


def test_regions_are_clamped_to_the_image() -> None:
    # Dilation can push a box past the edge; a region outside the canvas would
    # crash the crop/paste in apply_blur.
    detector = LabelHeuristicDetector()
    regions = detector.detect(
        checkered(100, 60), [{"category": "pedestrian", "box2d": [0.0, 0.0, 100.0, 60.0]}]
    )
    assert regions
    for region in regions:
        assert 0 <= region.x1 <= region.x2 <= 100
        assert 0 <= region.y1 <= region.y2 <= 60


def test_degenerate_and_malformed_boxes_are_skipped() -> None:
    detector = LabelHeuristicDetector()
    assert (
        detector.detect(
            checkered(),
            [
                {"category": "car", "box2d": [50.0, 50.0, 50.0, 50.0]},  # zero area
                {"category": "car", "box2d": [90.0, 90.0, 10.0, 10.0]},  # inverted
                {"category": "car", "box2d": "nonsense"},
                {"category": "car"},
                {"category": "pedestrian", "box2d": [1.0, 1.0, 3.0, 3.0]},  # sub-pixel
            ],
        )
        == []
    )


def test_blurring_actually_destroys_detail() -> None:
    image = checkered()
    box = (40, 20, 90, 70)
    before = variance(image, box)
    blurred = apply_blur(image, [BlurRegion(40, 20, 90, 70, "face")])
    after = variance(blurred, box)
    # A checkerboard has very high variance; blurring must collapse it.
    assert after < before * 0.3, (before, after)


def test_blurring_leaves_the_rest_of_the_frame_untouched() -> None:
    image = checkered()
    blurred = apply_blur(image, [BlurRegion(0, 0, 40, 40, "face")])
    untouched = (120, 80, 200, 120)
    assert image.crop(untouched).tobytes() == blurred.crop(untouched).tobytes()


def test_blurring_does_not_mutate_the_source() -> None:
    image = checkered()
    original = image.tobytes()
    apply_blur(image, [BlurRegion(0, 0, 50, 50, "face")])
    assert image.tobytes() == original


def test_no_regions_still_counts_as_blurred() -> None:
    """ "Nothing to blur" is not "blurring failed".

    Conflating them would either hide clean frames or, far worse, display
    unprocessed ones.
    """

    result = anonymize_frame(checkered(), [], detector=NullDetector())
    assert result.blurred is True
    assert result.region_count == 0
    assert result.error is None


def test_detector_failure_fails_closed() -> None:
    class Exploding:
        def detect(self, image, objects=None):  # type: ignore[no-untyped-def]
            raise RuntimeError("detector crashed")

    result = anonymize_frame(checkered(), [], detector=Exploding())  # type: ignore[arg-type]
    # blurred=False is what excludes the frame from every display path.
    assert result.blurred is False
    assert "detector crashed" in (result.error or "")


def test_end_to_end_blurs_a_pedestrian_head() -> None:
    image = checkered()
    objects = [{"category": "pedestrian", "box2d": [50.0, 20.0, 90.0, 100.0]}]
    result = anonymize_frame(image, objects)
    assert result.blurred and result.region_count == 1
    head = (52, 22, 88, 48)
    assert variance(result.image, head) < variance(image, head) * 0.5
