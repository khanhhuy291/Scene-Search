"""The env template and loader must agree across native and Docker entrypoints."""

import os
import subprocess
import sys

from core.config import APP_ENV_FILE, Settings
from services.validate_config import key_errors


def test_template_contains_only_supported_keys():
    assert key_errors(APP_ENV_FILE.with_name(".env.example")) == []


def test_checker_detects_misspelled_and_duplicate_keys_without_values(tmp_path):
    path = tmp_path / ".env"
    path.write_text("SEARCH_RERANK_ENABLE=private-value\nLLM_TIMEOUT=10\nLLM_TIMEOUT=20\n")
    errors = key_errors(path)
    assert errors == ["Unknown variable: SEARCH_RERANK_ENABLE", "Duplicate variable: LLM_TIMEOUT"]
    assert "private-value" not in str(errors)


def test_native_settings_do_not_read_cwd_env(tmp_path):
    (tmp_path / ".env").write_text("APP_NAME=unexpected-cwd-config\n")
    app_root = APP_ENV_FILE.parent
    env = {**os.environ, "PYTHONPATH": str(app_root)}
    script = "from core.config import AppSettings; print(AppSettings().name)"

    def name(cwd):
        return subprocess.check_output(
            [sys.executable, "-c", script], cwd=cwd, env=env, text=True
        ).strip()

    assert name(app_root) == name(app_root.parent) == name(tmp_path)
    assert name(tmp_path) != "unexpected-cwd-config"


def test_environment_overrides_dotenv_for_each_settings_group(monkeypatch, tmp_path):
    path = tmp_path / ".env"
    path.write_text("SEARCH_MODE=qwen\nQWEN_EMBEDDING_TIMEOUT=111\n")
    monkeypatch.setenv("SEARCH_MODE", "siglip")
    from core.config import MLSettings, SearchSettings

    assert SearchSettings(_env_file=path).mode == "siglip"
    assert MLSettings(_env_file=path).qwen_embedding_timeout == 111


def test_tests_do_not_load_deployment_defaults():
    assert Settings().video.sample_fps == 1.0


def test_compose_honors_app_options_and_only_overrides_network_routing(tmp_path):
    import json
    import shutil

    import pytest

    if shutil.which("docker") is None:
        pytest.skip("Docker Compose is required to check the rendered configuration")
    root = APP_ENV_FILE.parent.parent
    shutil.copy(root / "docker-compose.yml", tmp_path / "docker-compose.yml")
    (tmp_path / "app").mkdir()
    sample = APP_ENV_FILE.with_name(".env.example").read_text()
    changes = {
        "SEARCH_MODE=qwen": "SEARCH_MODE=siglip",
        "QDRANT_COLLECTION=scenes_local": "QDRANT_COLLECTION=test_collection",
        "QWEN_EMBEDDING_TIMEOUT=300": "QWEN_EMBEDDING_TIMEOUT=99",
        "APP_DEBUG=false": "APP_DEBUG=true",
        "ML_DTYPE=float16": "ML_DTYPE=bfloat16",
        "QWEN_EMBEDDING_BATCH_SIZE=1": "QWEN_EMBEDDING_BATCH_SIZE=3",
        "HTTP_PORT=5173": "HTTP_PORT=8088",
    }
    for old, new in changes.items():
        sample = sample.replace(old, new)
    (tmp_path / "app/.env").write_text(sample)
    result = subprocess.run(
        ["docker", "compose", "--env-file", "app/.env", "config", "--format", "json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    services = json.loads(result.stdout)["services"]
    for service in ["api", "worker", "embedding-api"]:
        env = services[service]["environment"]
        assert env["SEARCH_MODE"] == "siglip"
        assert env["QDRANT_COLLECTION"] == "test_collection"
        assert env["QWEN_EMBEDDING_TIMEOUT"] == "99"
        assert env["APP_DEBUG"] == "true"
        assert env["ML_DTYPE"] == "bfloat16"
        assert env["QDRANT_URL"] == "http://qdrant:6333"
    assert services["embedding-api"]["environment"]["ML_BATCH_SIZE"] == "3"
    assert services["embedding-api"]["environment"]["QWEN_EMBEDDING_URL"] == ""
    assert services["api"]["environment"]["QWEN_EMBEDDING_URL"] == "http://embedding-api:8001"
    assert services["frontend"]["ports"][0]["published"] == "8088"
