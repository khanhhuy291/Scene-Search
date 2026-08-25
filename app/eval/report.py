"""Render a report, and fail a build when retrieval regresses.

Two consumers with opposite needs. A person reads the markdown and needs to see
what was *not* measured as prominently as what was. CI reads the JSON and needs
one comparable number per band that does not move when a test is added.

The regression gate (FR-EVAL-05) compares precision@10 against a committed
baseline and fails on a drop of more than 5%. Three deliberate choices in it:

* **Relative, not absolute.** A 5% drop from 0.62 is a regression; a band that has
  always sat at 0.31 is not failing every build.
* **A band that becomes UNAVAILABLE fails too.** Losing the ability to measure
  something is a regression in the evaluation, and it is the failure most likely
  to be introduced accidentally — by a renamed payload field, or a ground-truth
  file that stopped being mounted.
* **A failed abstention control fails the build outright**, with no tolerance. It
  means a query with no possible answer returned results, which is worse for a
  user than a few points of precision.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict
from pathlib import Path

from eval.runner import Report

# FR-EVAL-05. Relative drop, not absolute points.
REGRESSION_TOLERANCE = 0.05


def _fmt(value: float, places: int = 3) -> str:
    return "—" if math.isnan(value) else f"{value:.{places}f}"


def to_json(report: Report) -> dict[str, object]:
    return {
        "label": report.label,
        "latency_p50_ms": report.latency_p50_ms,
        "latency_p95_ms": report.latency_p95_ms,
        "controls_passed": report.controls_passed,
        "controls_failed": report.controls_failed,
        "join_rate": report.join_rate,
        "corpus_videos": report.corpus_videos,
        "corpus_keyframes": report.corpus_keyframes,
        "bands": {
            band.band: {
                "scored": band.scored,
                "unavailable": band.unavailable,
                "reason": band.reason,
                "precision_at_5": band.precision_at_5,
                "precision_at_10": band.precision_at_10,
                "recall_at_50": band.recall_at_50,
                "ndcg_at_10": band.ndcg_at_10,
                "mrr": band.mrr,
            }
            for band in report.bands
        },
        "cases": [asdict(case) for case in report.cases],
        "notes": report.notes,
    }


def save_json(report: Report, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_json(report), indent=2, sort_keys=True), encoding="utf-8")
    return path


def to_markdown(report: Report) -> str:
    lines: list[str] = []
    title = f"# Retrieval evaluation{f' — {report.label}' if report.label else ''}"
    lines += [title, ""]

    if report.corpus_videos or report.corpus_keyframes:
        lines.append(
            f"Corpus: {report.corpus_keyframes:,} keyframes across {report.corpus_videos:,} videos."
        )
        lines.append("")

    # The join rate goes first, above every metric, because if it is low then
    # nothing below it means what it appears to mean.
    if not math.isnan(report.join_rate):
        if report.join_rate < 0.66:
            lines += [
                f"> **The ground-truth join covered only {report.join_rate:.0%} of results.**",
                "> The scores below describe a broken join between the index's video ids",
                "> and the label table's, not the quality of retrieval. Fix the join",
                "> before reading any number in this report.",
                "",
            ]
        else:
            lines += [f"Ground-truth join covered {report.join_rate:.0%} of returned results.", ""]

    lines += ["## Per band", ""]
    lines += [
        "| Band | Scored | P@5 | P@10 | R@50 | nDCG@10 | MRR |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for band in report.bands:
        if not band.is_available:
            lines.append(f"| {band.band} | **unavailable** | — | — | — | — | — |")
            continue
        lines.append(
            f"| {band.band} | {band.scored} | {_fmt(band.precision_at_5)} | "
            f"{_fmt(band.precision_at_10)} | {_fmt(band.recall_at_50)} | "
            f"{_fmt(band.ndcg_at_10)} | {_fmt(band.mrr)} |"
        )
    lines.append("")

    unavailable = [band for band in report.bands if not band.is_available]
    if unavailable:
        lines += ["### Why a band is unavailable", ""]
        for band in unavailable:
            lines.append(f"- **{band.band}** — {band.reason}")
        lines.append("")

    lines += ["## Abstention controls", ""]
    total_controls = report.controls_passed + report.controls_failed
    if total_controls:
        lines.append(
            f"{report.controls_passed}/{total_controls} queries with no possible answer "
            "returned nothing, as they should."
        )
        failed = [c for c in report.cases if c.status == "control_fail"]
        if failed:
            lines.append("")
            lines.append("Failures — each of these returned results for an unanswerable query:")
            lines.append("")
            for case in failed:
                lines.append(f"- `{case.case_id}` — {case.query!r}: {case.reason}")
        lines.append("")

    lines += ["## Latency", ""]
    lines += [
        "| | ms |",
        "| --- | ---: |",
        f"| p50 | {_fmt(report.latency_p50_ms, 1)} |",
        f"| p95 | {_fmt(report.latency_p95_ms, 1)} |",
        "",
    ]

    # Found-the-clip-but-showed-the-wrong-moment. Separated because it points at a
    # different fix from a retrieval miss, and it is invisible in precision alone.
    keyframe_misses = [c for c in report.cases if c.is_scored and c.keyframe_misses]
    if keyframe_misses:
        lines += [
            "## Right video, wrong moment",
            "",
            "These queries retrieved a video that does contain a qualifying frame, but",
            "surfaced a keyframe that does not. That is a keyframe-selection problem,",
            "not a retrieval one.",
            "",
            "| Query | Videos found | Wrong moment shown |",
            "| --- | ---: | ---: |",
        ]
        for case in keyframe_misses:
            lines.append(f"| `{case.case_id}` | {case.video_level_hits} | {case.keyframe_misses} |")
        lines.append("")

    lines += ["## Per query", ""]
    lines += [
        "| Query | Band | Status | Returned | P@10 | R@50 | RR | ms |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for case in report.cases:
        lines.append(
            f"| `{case.case_id}` | {case.band} | {case.status} | {case.returned} | "
            f"{_fmt(case.precision_at_10)} | {_fmt(case.recall_at_50)} | "
            f"{_fmt(case.reciprocal_rank)} | {case.took_ms:.0f} |"
        )
    lines.append("")

    errors = [c for c in report.cases if c.status == "error"]
    if errors:
        lines += ["## Queries that raised", ""]
        for case in errors:
            lines.append(f"- `{case.case_id}` — {case.reason}")
        lines.append("")

    if report.notes:
        lines += ["## Notes", ""]
        lines += [f"- {note}" for note in report.notes]
        lines.append("")

    return "\n".join(lines)


def save_markdown(report: Report, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_markdown(report), encoding="utf-8")
    return path


# -- the CI gate --------------------------------------------------------------


class Regression(RuntimeError):
    """Retrieval got worse, or stopped being measurable."""


def compare_to_baseline(
    report: Report,
    baseline_path: str | Path,
    *,
    tolerance: float = REGRESSION_TOLERANCE,
) -> list[str]:
    """Return the failures. Empty list means the build passes.

    Returning failures rather than raising lets a caller print all of them at once
    — being told about one regression, fixing it, and then discovering a second is
    a slow way to learn about two.
    """

    path = Path(baseline_path)
    if not path.exists():
        return [
            f"no baseline at {path}. Record one with "
            f"`python -m eval.cli --save-baseline {path}` once the numbers are trusted."
        ]

    baseline = json.loads(path.read_text(encoding="utf-8"))
    failures: list[str] = []

    if report.controls_failed:
        failures.append(
            f"{report.controls_failed} abstention control(s) returned results. "
            "A query with no possible answer must return nothing."
        )

    current_bands = {band.band: band for band in report.bands}
    for name, recorded in baseline.get("bands", {}).items():
        was = recorded.get("precision_at_10")
        if was is None or (isinstance(was, float) and math.isnan(was)):
            continue
        band = current_bands.get(name)
        if band is None or not band.is_available:
            failures.append(
                f"band {name!r} was scored in the baseline (P@10 {was:.3f}) and is now "
                "unavailable. Losing a measurement is a regression."
            )
            continue
        now = band.precision_at_10
        if math.isnan(now):
            failures.append(f"band {name!r}: precision@10 is not a number")
            continue
        if was > 0 and (was - now) / was > tolerance:
            failures.append(
                f"band {name!r}: precision@10 {was:.3f} → {now:.3f} "
                f"({(now - was) / was:+.1%}, tolerance {tolerance:.0%})"
            )

    return failures


__all__ = [
    "REGRESSION_TOLERANCE",
    "Regression",
    "compare_to_baseline",
    "save_json",
    "save_markdown",
    "to_json",
    "to_markdown",
]
