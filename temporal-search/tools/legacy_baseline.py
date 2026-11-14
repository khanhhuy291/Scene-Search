"""Capture/verify the legacy workspace without importing or starting the app.

Python 3.9+, standard library only. Output belongs under ignored data/.
No credentials, environment files, full Docker inspection, or model loads.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
NEW_PREFIXES = ("temporal-search/", "docs/temporal-search/")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8").rstrip()


def legacy_paths():
    raw = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
    )
    paths = set(raw.decode("utf-8").split("\0")) - {""}
    return sorted(path for path in paths if not path.startswith(NEW_PREFIXES))


def file_record(path):
    source = ROOT / path
    if not source.is_file():
        return {"state": "missing"}
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"state": "present", "sha256": digest.hexdigest(), "bytes": source.stat().st_size}


def sanitized(value):
    if isinstance(value, dict):
        return {
            key: ("[redacted]" if any(word in key.lower() for word in
                    ("password", "secret", "token", "authorization", "cookie")) else sanitized(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitized(item) for item in value]
    if isinstance(value, str) and value.startswith(("http://", "https://", "/api/")):
        parsed = urlsplit(value)
        # Strip userinfo, query parameters and fragments from persisted media URLs.
        return urlunsplit((parsed.scheme, parsed.netloc.split("@")[-1], parsed.path, "", ""))
    return value


def probe(url, payload=None, timeout=3):
    started = time.perf_counter()
    request = Request(url, headers={"Accept": "application/json"})
    if payload is not None:
        request.data = json.dumps(payload).encode("utf-8")
        request.add_header("Content-Type", "application/json")
    # Optional caller token stays in memory and is never persisted.
    token = os.environ.get("TEMPORAL_BASELINE_BEARER")
    if token:
        request.add_header("Authorization", "Bearer " + token)
    try:
        with urlopen(request, timeout=timeout) as response:
            content = response.read(4 * 1024 * 1024 + 1)
            if len(content) > 4 * 1024 * 1024:
                return {"state": "response_too_large", "http_status": response.status}
            try:
                body = sanitized(json.loads(content))
            except (ValueError, UnicodeDecodeError):
                body = None
            return {"state": "reachable", "http_status": response.status, "body": body,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 2)}
    except HTTPError as error:
        return {"state": "http_error", "http_status": error.code}
    except (URLError, TimeoutError, OSError) as error:
        return {"state": "unavailable", "error_type": type(error).__name__}


def command_probe(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"state": "unavailable", "error_type": type(error).__name__}
    if result.returncode:
        return {"state": "unavailable", "exit_code": result.returncode}
    return {"state": "available", "lines": result.stdout.strip().splitlines()}


def save(path, value):
    destination = Path(path).resolve()
    allowed = (ROOT / "data" / "temporal-search").resolve()
    if allowed not in destination.parents:
        raise ValueError("Output must be below data/temporal-search/ in this workspace")
    if destination.exists():
        raise ValueError("Refusing to overwrite an existing snapshot; choose a new output name")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    capture = subparsers.add_parser("capture")
    capture.add_argument("--output", required=True)
    capture.add_argument("--api-url", default="http://127.0.0.1:8000")
    capture.add_argument("--include-search", action="store_true")
    capture.add_argument("--search-timeout", type=float, default=60)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--baseline", required=True)
    args = parser.parse_args()
    if args.action == "verify":
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        changed = [path for path, record in baseline["files"].items() if file_record(path) != record]
        added = sorted(set(legacy_paths()) - set(baseline["files"]))
        report = {"checked_files": len(baseline["files"]), "changed": changed,
                  "added_legacy_paths": added, "head_unchanged": git("rev-parse", "HEAD") == baseline["git_head"]}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return int(bool(changed or added or not report["head_unchanged"]))

    base = args.api_url.rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost") or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError("The baseline collector accepts only a local HTTP API origin")
    health = probe(base + "/health")
    search = {"state": "not_requested", "samples": []}
    if args.include_search:
        search["state"] = "not_run_api_unavailable"
        if health.get("http_status") == 200:
            search["state"] = "attempted"
            for query in ("dashcam driving scene", "a pedestrian crossing the road", "a car changes lanes"):
                request = {"query": query, "limit": 5}
                search["samples"].append({"request": request,
                    "response": probe(base + "/api/v1/search", request, args.search_timeout)})
    snapshot = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "client_timezone": "Asia/Saigon", "git_head": git("rev-parse", "HEAD"),
        "git_status": git("status", "--short").splitlines(),
        "excluded_new_prefixes": NEW_PREFIXES,
        "files": {path: file_record(path) for path in legacy_paths()},
        "legacy_api_health": health,
        "legacy_openapi": probe(base + "/openapi.json") if health.get("http_status") == 200 else {"state": "not_run_api_unavailable"},
        "docker": command_probe(["docker", "ps", "--format", "{{.Names}} {{.Status}}"]),
        "gpu": command_probe(["nvidia-smi", "--query-gpu=name,memory.total,memory.used,driver_version", "--format=csv,noheader"]),
        "search": search,
        "notes": ["Source hashes describe the current working tree, including existing uncommitted changes.",
                  "Search samples are regression evidence, not labeled quality evaluation or a latency benchmark.",
                  "No service is started/stopped; no environment variables or secrets are serialized."],
    }
    save(args.output, snapshot)
    print(json.dumps({"output": str(Path(args.output)), "protected_files": len(snapshot["files"]),
                      "api": health["state"], "search": search["state"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
