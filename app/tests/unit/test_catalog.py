"""Huy's payload shape: structured fields are evidence, not decoration."""

from __future__ import annotations

import pytest

from search.catalog import keyframe_from_payload, structured_polarity

HUY_PAYLOAD = {
    "video_id": "video-huy",
    "timestamp_sec": 12.5,
    "frame_no": 375,
    "caption": (
        "A dashcam view from a vehicle driving down a tree-lined residential "
        "street, with multiple cars parked along the sides and a few pedestrians "
        "visible in the distance. The sky is bright and sunny, suggesting a clear day."
    ),
    "vehicles": [
        "black suv",
        "white sedan",
        "white minivan",
        "white station wagon",
        "red and black cars",
    ],
    "people": [
        "person wearing red shirt standing on the sidewalk",
        "pedestrian in red shirt crossing the road",
    ],
    "environment": {
        "weather": "sunny",
        "time_of_day": "daytime",
        "road_condition": "dry",
    },
    "traffic_elements": ["green street sign", "road signs", "stop sign"],
    "ocr": "BROOKLYN",
    "minio_thumbnail_key": "thumbnails/huy.jpg",
    "minio_video_key": "videos/huy.mov",
}


def test_huy_payload_is_read_into_a_keyframe() -> None:
    frame = keyframe_from_payload("p1", HUY_PAYLOAD)
    assert frame is not None
    assert frame.video_id == "video-huy"
    assert frame.ocr == "BROOKLYN"
    assert frame.weather == "sunny"
    assert frame.time_of_day == "daytime"
    assert frame.road_condition == "dry"
    assert frame.people is not None and len(frame.people) == 2
    assert "black suv" in frame.vehicles


def test_sunny_is_clear_sky_and_not_rain() -> None:
    frame = keyframe_from_payload("p1", HUY_PAYLOAD)
    assert structured_polarity(frame, "clear_sky") == "present"
    assert structured_polarity(frame, "rain") == "absent"
    assert structured_polarity(frame, "snow") == "absent"


def test_people_list_is_observed_presence() -> None:
    frame = keyframe_from_payload("p1", HUY_PAYLOAD)
    assert structured_polarity(frame, "people") == "present"


def test_empty_people_list_is_observed_absence() -> None:
    payload = {**HUY_PAYLOAD, "people": []}
    frame = keyframe_from_payload("p1", payload)
    assert structured_polarity(frame, "people") == "absent"


def test_missing_people_key_falls_back_to_caption() -> None:
    payload = {k: v for k, v in HUY_PAYLOAD.items() if k != "people"}
    frame = keyframe_from_payload("p1", payload)
    assert frame is not None
    assert frame.people is None
    assert structured_polarity(frame, "people") == "unknown"


def test_suv_phrase_confirms_car() -> None:
    frame = keyframe_from_payload("p1", HUY_PAYLOAD)
    assert structured_polarity(frame, "car") == "present"
    assert structured_polarity(frame, "truck") == "unknown"


def test_dry_road_is_not_wet() -> None:
    frame = keyframe_from_payload("p1", HUY_PAYLOAD)
    assert structured_polarity(frame, "wet_road") == "absent"


def test_legacy_qwen_caption_still_loads() -> None:
    frame = keyframe_from_payload(
        "p1",
        {"video_id": "v", "qwen_caption": "Rain on the road.", "timestamp_sec": 1.0},
    )
    assert frame is not None
    assert frame.caption.startswith("Rain")
    assert frame.people is None


def test_viettech_frame_id_recovers_timestamp() -> None:
    """The live Scences payload has frame_00034.jpg and no timestamp_sec."""

    frame = keyframe_from_payload(
        "p1",
        {
            "video_id": "024b275b-bbfdf5ee",
            "frame_id": "00034",
            "frame_name": "frame_00034.jpg",
            "minio_path": "frames/024b275b-bbfdf5ee/frame_00034.jpg",
        },
    )
    assert frame is not None
    assert frame.frame_no == 34
    assert frame.timestamp_s == pytest.approx(6.8)
    assert frame.thumbnail_key == "frames/024b275b-bbfdf5ee/frame_00034.jpg"


def test_explicit_timestamp_wins_and_raw_video_is_not_publishable() -> None:
    frame = keyframe_from_payload(
        "p1",
        {
            "video_id": "00268999-9f6d5823",
            "qwen_caption": "A sunny highway.",
            "timestamp_sec": 3.993,
            "frame_no": 120,
            "frame_minio_key": "frames/00268999-9f6d5823/frame_00008.jpg",
            "raw_minio_key": "videos/00268999-9f6d5823.mov",
        },
    )
    assert frame is not None
    assert frame.timestamp_s == pytest.approx(3.993)
    assert frame.frame_no == 120
    assert frame.thumbnail_key == "frames/00268999-9f6d5823/frame_00008.jpg"
    assert frame.video_key is None
    assert not frame.renderable


def test_seed_top_level_weather_is_read() -> None:
    frame = keyframe_from_payload(
        "p1",
        {"video_id": "v", "weather": "snowy", "timeofday": "daytime"},
    )
    assert structured_polarity(frame, "snow") == "present"
    assert structured_polarity(frame, "rain") == "absent"
    assert structured_polarity(frame, "day") == "present"


def test_segment_payload_preserves_filter_and_rendering_fields() -> None:
    frame = keyframe_from_payload(
        "segment-point",
        {
            "video_id": "video-a",
            "dataset": "uploads",
            "granularity": "segment",
            "ts_start_s": 5.0,
            "ts_end_s": 9.5,
            "thumbnail_key": "thumbnails/video-a/preview.jpg",
            "objects": ["car", "person"],
            "object_counts": {"car": 2},
            "behaviors": ["cut_in"],
        },
    )

    assert frame is not None
    assert frame.granularity == "segment"
    assert frame.end_timestamp_s == 9.5
    assert frame.dataset == "uploads"
    assert frame.thumbnail_key == "thumbnails/video-a/preview.jpg"
    assert frame.video_key is None
    assert frame.objects == ("car", "person")
    assert frame.object_counts == {"car": 2}
    assert frame.behaviors == ("cut_in",)
