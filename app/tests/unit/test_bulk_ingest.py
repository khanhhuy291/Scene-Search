"""Bulk uploader resume and uncertain-upload behavior, without submitting videos."""

import argparse
import json
from unittest.mock import Mock

import pytest
from starlette.datastructures import Headers
from starlette.formparsers import MultiPartParser

from scripts import bulk_ingest


def setup_batch(tmp_path, monkeypatch, initial_status=None):
    source = tmp_path / "videos"
    source.mkdir()
    video = source / "clip.mov"
    video.write_bytes(b"fixture-not-a-real-video")
    state_path = tmp_path / "manifest.json"
    args = argparse.Namespace(
        source=source,
        recursive=False,
        limit=None,
        dry_run=False,
        state=state_path,
        env_file=tmp_path / ".env",
        email=None,
        api_url="http://localhost:8000/api/v1",
        request_timeout=30,
        task_timeout=60,
        poll_interval=0.01,
        max_consecutive_failures=5,
        retry_failed=False,
    )
    if initial_status:
        stat = video.stat()
        state_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "source": str(source),
                    "api_url": args.api_url,
                    "files": {
                        "clip.mov": {
                            "signature": {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns},
                            "task_id": "existing-task",
                            "status": initial_status,
                        }
                    },
                }
            )
        )
    api = Mock()
    monkeypatch.setattr(bulk_ingest, "credentials", lambda *_: ("admin@example.com", "secret"))
    monkeypatch.setattr(bulk_ingest, "API", lambda *_: api)
    return args, api


def test_resume_pending_task_does_not_upload_again(tmp_path, monkeypatch):
    args, api = setup_batch(tmp_path, monkeypatch, initial_status="processing")

    def request(method, path, **kwargs):
        if path == "/admin/embedding-model":
            return {"state": "ready"}
        assert (method, path) == ("GET", "/tasks/existing-task")
        return {"status": "completed", "progress": 100, "result": {"scenes_indexed": 2}}

    api.request.side_effect = request
    assert bulk_ingest.run(args) == 0
    assert all(call.args[0] == "GET" for call in api.request.call_args_list)
    assert json.loads(args.state.read_text())["files"]["clip.mov"]["status"] == "completed"


def test_resume_completed_file_is_skipped(tmp_path, monkeypatch):
    args, api = setup_batch(tmp_path, monkeypatch, initial_status="completed")
    api.request.return_value = {"state": "ready"}
    assert bulk_ingest.run(args) == 0
    api.request.assert_called_once_with("GET", "/admin/embedding-model")


def test_lost_upload_response_is_saved_and_not_resubmitted(tmp_path, monkeypatch):
    args, api = setup_batch(tmp_path, monkeypatch)

    def request(method, path, **kwargs):
        if path == "/admin/embedding-model":
            return {"state": "ready"}
        raise TimeoutError("response lost after upload")

    api.request.side_effect = request
    with pytest.raises(TimeoutError):
        bulk_ingest.run(args)
    assert json.loads(args.state.read_text())["files"]["clip.mov"]["status"] == "upload_unknown"
    api.request.reset_mock()
    with pytest.raises(RuntimeError, match="outcome is uncertain"):
        bulk_ingest.run(args)
    api.request.assert_called_once_with("GET", "/admin/embedding-model")


@pytest.mark.asyncio
async def test_streamed_multipart_is_readable_as_fastapi_upload(tmp_path, monkeypatch):
    video = tmp_path / "video.mov"
    content = b"video-fixture" * 100_000
    video.write_bytes(content)
    connection = Mock()
    captured = {}

    def send(method, path, *, body, headers):
        captured.update(parts=list(body), headers=headers)

    connection.request.side_effect = send
    response = connection.getresponse.return_value
    response.status = 202
    response.read.return_value = b'{"task_id":"new-task","status":"queued"}'
    monkeypatch.setattr(bulk_ingest.http.client, "HTTPConnection", lambda *a, **kw: connection)
    api = bulk_ingest.API("http://localhost:8000/api/v1", "admin@example.com", "secret", 30)
    result = api.request("POST", "/ingest/upload", file=video)
    assert result["task_id"] == "new-task"
    assert sum(map(len, captured["parts"])) == int(captured["headers"]["Content-Length"])

    async def stream():
        for part in captured["parts"]:
            yield part

    form = await MultiPartParser(Headers(captured["headers"]), stream()).parse()
    uploaded = form["file"]
    try:
        assert uploaded.filename == "video.mov"
        assert await uploaded.read() == content
    finally:
        await uploaded.close()


def test_model_failure_before_upload_does_not_create_an_uncertain_record(tmp_path, monkeypatch):
    args, api = setup_batch(tmp_path, monkeypatch)
    api.request.side_effect = [{"state": "ready"}, {"state": "error"}]
    with pytest.raises(RuntimeError, match="Embedding model is error"):
        bulk_ingest.run(args)
    assert all(call.args[0] == "GET" for call in api.request.call_args_list)
    assert not args.state.exists()
