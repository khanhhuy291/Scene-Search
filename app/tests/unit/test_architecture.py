"""Phase 1 architecture invariants."""

from __future__ import annotations

import tomllib
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = APP_ROOT.parent


def test_api_main_is_the_only_application_entrypoint() -> None:
    assert (APP_ROOT / "api/main.py").is_file()
    assert not (APP_ROOT / "main.py").exists()

    runtime_files = [
        APP_ROOT / "Makefile",
        APP_ROOT / "Dockerfile",
        REPOSITORY_ROOT / "docker-compose.yml",
    ]
    for path in runtime_files:
        contents = path.read_text(encoding="utf-8")
        assert "api.main:app" in contents, path
        assert "uvicorn main:app" not in contents, path


def test_legacy_template_packages_are_absent() -> None:
    for package in ("agents", "models"):
        assert not list((APP_ROOT / package).rglob("*.py")), package
    for relative_path in ("api/routes.py", "config.py", "services/llm.py"):
        assert not (APP_ROOT / relative_path).exists(), relative_path


def test_manifest_has_no_template_agent_dependencies() -> None:
    with (APP_ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]

    dependencies = "\n".join(project["dependencies"]).lower()
    for package in ("langchain", "langgraph", "openai"):
        assert package not in dependencies
