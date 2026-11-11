#!/usr/bin/env python3
"""Stream local videos through the public ingestion API, one job at a time.

Requires only Python 3.11+ on the host. Does not write directly to MinIO,
PostgreSQL or Qdrant. Credentials and tokens are never written to the manifest.
"""

from __future__ import annotations

import argparse
import fcntl
import getpass
import http.client
import json
import mimetypes
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
SUFFIXES = {".mov", ".mp4", ".mkv", ".webm"}
TERMINAL = {"completed", "failed", "cancelled"}
MAX_UPLOAD = 500 * 1024 * 1024


def now() -> str:
    return datetime.now(UTC).isoformat()


def emit(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def credentials(env_file: Path, email: str | None) -> tuple[str, str]:
    values = {}
    if env_file.is_file():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                values[key.strip()] = value
    selected_email = email or os.getenv("LOCAL_ADMIN_EMAIL") or values.get("LOCAL_ADMIN_EMAIL")
    if not selected_email:
        raise ValueError("Set LOCAL_ADMIN_EMAIL or pass --email")
    password = os.getenv("LOCAL_ADMIN_PASSWORD") or values.get("LOCAL_ADMIN_PASSWORD")
    if not password:
        password = getpass.getpass(f"Password for {selected_email}: ")
    return selected_email, password


class APIError(RuntimeError):
    def __init__(self, status: int, detail: str):
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status


class API:
    def __init__(self, base_url: str, email: str, password: str, timeout: float):
        self.url = urlsplit(base_url.rstrip("/"))
        if self.url.scheme not in {"http", "https"} or not self.url.hostname:
            raise ValueError("--api-url must be an HTTP(S) URL")
        if self.url.username or self.url.password or self.url.query or self.url.fragment:
            raise ValueError("--api-url cannot contain credentials, a query or a fragment")
        self.email, self.password, self.timeout = email, password, timeout
        self.token = ""

    def _request(self, method: str, path: str, payload=None, file: Path | None = None):
        connection_type = (
            http.client.HTTPSConnection
            if self.url.scheme == "https"
            else http.client.HTTPConnection
        )
        connection = connection_type(self.url.hostname, self.url.port, timeout=self.timeout)
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        body = None
        if file is not None:
            boundary = "scenesearch-" + uuid4().hex
            # Only the basename is sent, and quotes/newlines cannot enter MIME headers.
            filename = file.name.replace('"', "_").replace("\r", "_").replace("\n", "_")
            content_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            prefix = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode()
            suffix = f"\r\n--{boundary}--\r\n".encode()
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
            headers["Content-Length"] = str(len(prefix) + file.stat().st_size + len(suffix))

            def chunks():
                yield prefix
                with file.open("rb") as stream:
                    while chunk := stream.read(1024 * 1024):
                        yield chunk
                yield suffix

            body = chunks()
        elif payload is not None:
            body = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        try:
            target = self.url.path.rstrip("/") + path
            connection.request(method, target, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            try:
                result = json.loads(raw) if raw else {}
            except (ValueError, UnicodeDecodeError):
                raise RuntimeError(
                    f"Non-JSON response for {path} (HTTP {response.status})"
                ) from None
            if response.status >= 400:
                raise APIError(response.status, str(result.get("detail", "Request failed")))
            return result
        finally:
            connection.close()

    def login(self) -> None:
        result = self._request(
            "POST", "/auth/login", {"email": self.email, "password": self.password}
        )
        if result.get("user", {}).get("role") != "admin":
            raise ValueError("Bulk ingestion requires an admin account")
        self.token = result["access_token"]

    def request(self, method: str, path: str, payload=None, file: Path | None = None):
        try:
            return self._request(method, path, payload, file)
        except APIError as exc:
            if exc.status != 401:
                raise
            self.token = ""
            self.login()
            return self._request(method, path, payload, file)


def save(path: Path, data: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def wait_for_task(api: API, record: dict, interval: float, timeout: float, persist) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    errors = 0
    while True:
        try:
            task = api.request("GET", f"/tasks/{record['task_id']}")
            errors = 0
        except (OSError, http.client.HTTPException, APIError) as exc:
            if isinstance(exc, APIError) and exc.status < 500:
                raise
            errors += 1
            if errors >= 5:
                raise RuntimeError(
                    "Task polling unavailable; rerun to resume the saved task"
                ) from exc
            emit(f"Polling temporarily unavailable ({errors}/5): {exc}")
        else:
            record.update(
                status=task["status"],
                video_id=task.get("video_id"),
                progress=task.get("progress", 0),
                result=task.get("result"),
                error=task.get("error"),
                updated_at=now(),
            )
            persist()
            current = (record["status"], record["progress"])
            if current != last:
                emit(f"  task {record['task_id']}: {current[0]} {current[1]}%")
                last = current
            if record["status"] in TERMINAL:
                return task
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "Task wait timed out; worker may still run. Rerun to resume this task"
            )
        time.sleep(interval)


def run(args) -> int:
    source = args.source.resolve()
    if not source.is_dir():
        raise ValueError(f"Source directory does not exist: {source}")
    iterator = source.rglob("*") if args.recursive else source.iterdir()
    files = sorted(p for p in iterator if p.is_file() and p.suffix.lower() in SUFFIXES)
    if args.limit:
        files = files[: args.limit]
    if not files:
        raise ValueError("No supported videos found")
    for file in files:
        if not 0 < file.stat().st_size <= MAX_UPLOAD:
            raise ValueError(f"File is empty or larger than the API's 500 MiB limit: {file}")
    total_bytes = sum(file.stat().st_size for file in files)
    emit(f"Selected {len(files)} videos, {total_bytes / 1024**3:.2f} GiB from {source}")
    if args.dry_run:
        for file in files[:5]:
            emit(f"  {file.name} ({file.stat().st_size / 1024**2:.1f} MiB)")
        emit("Dry run: no login, uploads or jobs created")
        return 0

    state_path = args.state.resolve()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    # Prevent two copies of the uploader from racing on one manifest.
    with state_path.with_suffix(state_path.suffix + ".lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another uploader is using this state file") from None
        state = (
            json.loads(state_path.read_text())
            if state_path.exists()
            else {
                "version": 1,
                "source": str(source),
                "api_url": args.api_url.rstrip("/"),
                "created_at": now(),
                "files": {},
            }
        )
        if (
            state.get("version") != 1
            or state.get("source") != str(source)
            or state.get("api_url") != args.api_url.rstrip("/")
        ):
            raise ValueError("State belongs to another source/API; use a different --state path")
        email, password = credentials(args.env_file, args.email)
        api = API(args.api_url, email, password, args.request_timeout)
        api.login()
        model = api.request("GET", "/admin/embedding-model")
        if model["state"] not in {"ready", "busy"}:
            raise ValueError(f"Embedding model is {model['state']}; load it in the admin UI first")
        emit(f"Authenticated as admin; embedding model: {model['state']}")

        def persist():
            state["updated_at"] = now()
            save(state_path, state)

        consecutive_failures = 0
        for index, file in enumerate(files, 1):
            key = file.relative_to(source).as_posix()
            stat = file.stat()
            signature = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
            record = state["files"].get(key)
            emit(f"[{index}/{len(files)}] {key}")
            if record and record.get("signature") != signature:
                raise ValueError(f"File changed since last run: {key}; use another --state path")
            if record and record["status"] == "completed":
                emit("  skipped: already completed in this manifest")
                continue
            if record and record["status"] in {"failed", "cancelled", "upload_rejected"}:
                if not args.retry_failed:
                    emit("  skipped: previous failure; use --retry-failed to submit again")
                    continue
                record = None
            if record and not record.get("task_id"):
                raise RuntimeError(
                    f"Previous upload outcome is uncertain for {key}. Check /api/v1/tasks before "
                    "resubmitting; the script refuses to create a potentially concurrent duplicate"
                )
            if not record:
                model = api.request("GET", "/admin/embedding-model")
                if model["state"] not in {"ready", "busy"}:
                    raise RuntimeError(
                        f"Embedding model is {model['state']}; stop submitting videos and recover "
                        "the embedding service before resuming"
                    )
                record = {"signature": signature, "status": "uploading", "started_at": now()}
                state["files"][key] = record
                persist()
                try:
                    accepted = api.request("POST", "/ingest/upload", file=file)
                except APIError as exc:
                    record.update(
                        status="upload_unknown" if exc.status >= 500 else "upload_rejected",
                        error=str(exc),
                    )
                    persist()
                    raise
                except (OSError, http.client.HTTPException, RuntimeError) as exc:
                    record.update(status="upload_unknown", error=str(exc))
                    persist()
                    raise
                record.update(
                    task_id=accepted["task_id"],
                    video_id=accepted.get("video_id"),
                    status=accepted["status"],
                )
                persist()
            task = wait_for_task(api, record, args.poll_interval, args.task_timeout, persist)
            if task["status"] == "completed":
                result = task.get("result") or {}
                emit(
                    f"  completed: scenes={result.get('scenes_indexed', '?')}, "
                    f"vectors={result.get('vectors_indexed', '?')}, "
                    f"duplicate={result.get('duplicate', False)}"
                )
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                emit(f"  {task['status']}: {task.get('error')}")
                if consecutive_failures >= args.max_consecutive_failures:
                    raise RuntimeError(
                        "Too many consecutive failed jobs; inspect worker logs before resuming"
                    )

        selected = [state["files"].get(p.relative_to(source).as_posix(), {}) for p in files]
        summary = {"selected": len(files), "completed": 0, "failed": 0, "other": 0}
        for record in selected:
            if record.get("status") == "completed":
                summary["completed"] += 1
            elif record.get("status") in {"failed", "cancelled", "upload_rejected"}:
                summary["failed"] += 1
            else:
                summary["other"] += 1
        state["last_summary"] = summary
        persist()
        emit(f"Summary: {json.dumps(summary)}")
        emit(f"Manifest: {state_path}")
        return 1 if summary["failed"] or summary["other"] else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT / "bdd100k_videos_train_00/bdd100k/videos/train",
    )
    parser.add_argument("--api-url", default="http://localhost:8000/api/v1")
    parser.add_argument("--env-file", type=Path, default=ROOT / "app/.env")
    parser.add_argument(
        "--email", help="Admin email; password comes from env file/environment or a prompt"
    )
    parser.add_argument("--state", type=Path, default=ROOT / "data/ingestion/bdd100k_train_00.json")
    parser.add_argument("--limit", type=int, help="Only the first N videos, sorted by filename")
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=5)
    parser.add_argument("--request-timeout", type=float, default=300)
    parser.add_argument("--task-timeout", type=float, default=3600)
    parser.add_argument("--max-consecutive-failures", type=int, default=5)
    args = parser.parse_args()
    if (
        (args.limit is not None and args.limit < 1)
        or min(args.poll_interval, args.request_timeout, args.task_timeout) <= 0
        or args.max_consecutive_failures < 1
    ):
        parser.error("Limits, intervals and timeouts must be positive")
    try:
        return run(args)
    except KeyboardInterrupt:
        emit(
            "Stopped. Submitted jobs remain on the worker; rerun with the same state file to resume"
        )
        return 130
    except (OSError, http.client.HTTPException, ValueError, RuntimeError, KeyError) as exc:
        emit(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
