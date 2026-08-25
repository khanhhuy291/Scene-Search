"""Packaging invariants.

With four people adding dependencies in parallel, packaging mistakes are quiet:
the install still succeeds and something fails much later, in someone else's
branch. These checks are cheap and run on every PR.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def load() -> dict:
    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)


def requirement_names(entries: list[str]) -> set[str]:
    names = set()
    for entry in entries:
        match = re.match(r"^([A-Za-z0-9._-]+)", entry)
        if match:
            names.add(re.sub(r"[-_.]+", "-", match.group(1)).lower())
    return names


def test_ml_extra_includes_media_extra() -> None:
    """The ML stack must be a superset of the media stack.

    The two are listed separately so CI can install media without torch. If they
    drift, a worker built with only the ML extra loses video decoding and fails
    at runtime rather than at install time.
    """

    extras = load()["project"]["optional-dependencies"]
    media = requirement_names(extras["media"])
    ml = requirement_names(extras["ml"])
    assert media <= ml, f"ml extra is missing: {sorted(media - ml)}"


def test_media_extra_stays_free_of_the_model_stack() -> None:
    # The whole point of the split is that CI can run the decode and
    # anonymization tests without a ~500 MB torch download.
    media = requirement_names(load()["project"]["optional-dependencies"]["media"])
    heavy = {"torch", "torchvision", "open-clip-torch", "transformers", "ultralytics"}
    assert not (media & heavy), f"media extra pulls the model stack: {sorted(media & heavy)}"


def test_siglip_text_tower_dependencies_are_pinned() -> None:
    """SigLIP tokenizes through HuggingFace transformers.

    open_clip declares transformers only under its optional "training" extra, so
    without these the image tower works and the text tower raises ImportError --
    ingestion looks healthy while search cannot encode a query at all.
    """

    ml = requirement_names(load()["project"]["optional-dependencies"]["ml"])
    assert "transformers" in ml
    assert "sentencepiece" in ml


def test_new_top_level_packages_are_included_in_the_distribution() -> None:
    # The package allowlist is explicit, so a new top-level package is silently
    # excluded from the built distribution until it is added here.
    config = load()["tool"]["setuptools"]["packages"]["find"]["include"]
    patterns = {entry.rstrip("*") for entry in config}

    app_root = PYPROJECT.parent
    skip = {"tests", "docker", "scripts", "db"}
    for child in app_root.iterdir():
        if not child.is_dir() or child.name.startswith((".", "_")):
            continue
        if child.name in skip or not (child / "__init__.py").exists():
            continue
        assert child.name in patterns, (
            f"package {child.name!r} exists but is not in [tool.setuptools.packages.find].include"
        )
