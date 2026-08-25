"""Video decode, sampling, and preview settings."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.config import Settings, VideoSettings


def test_defaults_match_the_selected_corpus_annotation_rate() -> None:
    settings = VideoSettings()
    assert settings.sample_fps == 1.0
    assert settings.preview_fps == 5.0


def test_segment_shorter_than_two_samples_is_rejected() -> None:
    # A one-frame segment makes segment granularity identical to frame
    # granularity while still doubling the number of indexed points.
    with pytest.raises(ValidationError, match="too short"):
        VideoSettings(sample_fps=2.0, segment_seconds=0.4)


def test_segment_spanning_two_samples_is_accepted() -> None:
    assert VideoSettings(sample_fps=2.0, segment_seconds=1.0).segment_seconds == 1.0


@pytest.mark.parametrize("threshold", [0.4, 1.5])
def test_dedup_threshold_must_be_a_plausible_cosine(threshold: float) -> None:
    with pytest.raises(ValidationError):
        VideoSettings(dedup_threshold=threshold)


def test_dedup_can_be_disabled_for_ablation() -> None:
    # The evaluation reports a with/without deduplication ablation, so turning
    # it off has to be a supported configuration rather than a code edit.
    assert VideoSettings(dedup_enabled=False).dedup_enabled is False


@pytest.mark.parametrize("crf", [-1, 60])
def test_preview_crf_stays_in_the_h264_range(crf: int) -> None:
    with pytest.raises(ValidationError):
        VideoSettings(preview_crf=crf)


def test_video_settings_are_reachable_from_the_aggregate() -> None:
    assert Settings().video.segment_seconds == 5.0
