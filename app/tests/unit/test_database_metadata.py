from db.models import Base, IngestionTask


def test_ingestion_task_is_registered_for_alembic_autogeneration() -> None:
    table = Base.metadata.tables[IngestionTask.__tablename__]

    assert table.name == "ingestion_tasks"
    assert set(table.columns.keys()) == {
        "task_id",
        "video_path",
        "status",
        "progress",
        "result",
        "error",
        "error_code",
        "video_id",
        "celery_task_id",
        "pipeline_version",
        "started_at",
        "finished_at",
        "created_at",
        "updated_at",
    }
