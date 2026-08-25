"""Schema invariants that the delivery plan depends on.

These assert the shape of the metadata rather than database behaviour, so they
run without infrastructure. The corresponding runtime behaviour is covered by the
integration tests once Postgres is available.
"""

from __future__ import annotations

from db.models import Base


def _table(name: str):
    return Base.metadata.tables[name]


def _constraint_names(table_name: str) -> set[str]:
    table = _table(table_name)
    names = {c.name for c in table.constraints if c.name}
    names |= {index.name for index in table.indexes if index.name}
    return names


def test_all_expected_tables_are_registered() -> None:
    assert set(Base.metadata.tables) == {
        "videos",
        "frames",
        "segments",
        "frame_objects",
        "frame_attributes",
        "behavior_events",
        "users",
        "review_sessions",
        "review_decisions",
        "datasets",
        "ingestion_tasks",
    }


def test_video_checksum_is_unique() -> None:
    # This unique constraint is what makes ingestion idempotent; without it a
    # re-run silently duplicates the corpus.
    assert _table("videos").c.checksum.unique is True


def test_video_ingestion_status_is_explicit_and_constrained() -> None:
    videos = _table("videos")
    assert videos.c.ingestion_status.nullable is False
    assert "pending" in str(videos.c.ingestion_status.server_default.arg)
    check = next(
        constraint
        for constraint in videos.constraints
        if constraint.name == "ck_videos_ingestion_status_allowed"
    )
    for status in ("pending", "processing", "indexed", "failed", "deleting"):
        assert status in str(check.sqltext)


def test_frames_are_unique_within_a_video() -> None:
    assert "uq_frames_video_id_frame_index" in _constraint_names("frames")


def test_frames_default_to_blurred() -> None:
    # Fail closed (ADR-0003): a frame is never displayed merely because the
    # anonymization step did not run.
    blurred = _table("frames").c.blurred
    assert blurred.nullable is False
    assert blurred.server_default is not None
    assert "true" in str(blurred.server_default.arg).lower()


def test_dataset_export_requires_an_approved_session() -> None:
    """The human-in-the-loop gate, enforced by the database.

    A CHECK pins ``session_status`` to 'approved', and a composite foreign key
    ties it to the live status of the referenced session. Together they make an
    export from a draft, submitted, or rejected session unrepresentable.
    """

    datasets = _table("datasets")

    checks = {
        c.name: str(c.sqltext)
        for c in datasets.constraints
        if c.__class__.__name__ == "CheckConstraint"
    }
    assert "ck_datasets_source_session_approved" in checks
    assert "approved" in checks["ck_datasets_source_session_approved"]

    composite = [
        fk
        for fk in datasets.foreign_key_constraints
        if {"session_id", "session_status"} == {c.name for c in fk.columns}
    ]
    assert composite, "datasets must reference (id, status) on review_sessions"
    constraint = composite[0]
    assert constraint.ondelete == "RESTRICT"
    # Blocks un-approving a session that has already been exported, which would
    # otherwise leave a dataset whose stated provenance is no longer true.
    assert constraint.onupdate == "RESTRICT"


def test_review_sessions_expose_the_composite_target() -> None:
    assert "uq_review_sessions_id_status" in _constraint_names("review_sessions")


def test_approval_requires_a_distinct_approver() -> None:
    checks = {
        c.name
        for c in _table("review_sessions").constraints
        if c.__class__.__name__ == "CheckConstraint"
    }
    assert "ck_review_sessions_approved_requires_approver" in checks
    assert "ck_review_sessions_approver_differs_from_author" in checks


def test_roles_are_constrained_to_the_documented_set() -> None:
    check = next(
        c
        for c in _table("users").constraints
        if c.__class__.__name__ == "CheckConstraint" and c.name == "ck_users_role_allowed"
    )
    text = str(check.sqltext)
    for role in ("engineer", "admin"):
        assert role in text
    assert "reviewer" not in text


def test_video_previews_default_to_blurred() -> None:
    # Playback must fail closed the same way still display does: a clip whose
    # anonymization did not complete is never served (ADR-0003).
    preview_blurred = _table("videos").c.preview_blurred
    assert preview_blurred.nullable is False
    assert "true" in str(preview_blurred.server_default.arg).lower()


def test_raw_and_preview_assets_are_separate_columns() -> None:
    # The restricted original and the servable anonymized clip are distinct
    # keys, so no code path can accidentally serve one in place of the other.
    videos = _table("videos")
    assert "raw_object_key" in videos.c
    assert "preview_object_key" in videos.c


def test_segments_are_unique_within_a_video() -> None:
    assert "uq_segments_video_id_segment_index" in _constraint_names("segments")


def test_segment_keyframe_loss_does_not_delete_the_segment() -> None:
    # SET NULL, not CASCADE: a segment without a poster frame still has a valid
    # vector and time span and remains a legitimate search result.
    fk = next(
        fk
        for fk in _table("segments").foreign_key_constraints
        if {"keyframe_id"} == {c.name for c in fk.columns}
    )
    assert fk.ondelete == "SET NULL"


def test_frames_record_the_span_they_cover() -> None:
    # Deduplication folds a dropped frame's span into the frame that represents
    # it, so time coverage survives the cost saving.
    frames = _table("frames")
    assert "covers_start_s" in frames.c
    assert "covers_end_s" in frames.c


def test_frame_deletion_cascades_from_videos() -> None:
    # Deleting a video must not strand frames, which would leave Qdrant points
    # pointing at rows that no longer exist.
    fk = next(iter(_table("frames").foreign_key_constraints))
    assert fk.ondelete == "CASCADE"
