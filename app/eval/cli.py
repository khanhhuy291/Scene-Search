"""Command line for the evaluation harness.

    # against the attached index, with the tunnel up
    python -m eval.cli --mot-csv ../data/mot_labels.csv --out ../reports/eval

    # shape of the run without touching an index or a label file
    python -m eval.cli --dry-run

    # record the current numbers as the baseline CI compares against
    python -m eval.cli --mot-csv ... --save-baseline eval/baselines/live.json

    # fail the build if retrieval regressed
    python -m eval.cli --mot-csv ... --check-baseline eval/baselines/live.json

Exit codes: 0 pass, 1 regression or failed control, 2 could not run at all.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import cast

from eval.report import compare_to_baseline, save_json, save_markdown, to_json, to_markdown
from eval.runner import Engine, run_ablations, run_suite
from eval.suite import ATTRIBUTE, BEHAVIOURAL, COMPOSITIONAL, OBJECT, default_suite, predicates_of
from eval.truth import BehaviorGroundTruth, GroundTruth, MotGroundTruth


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="eval.cli", description=__doc__)
    ap.add_argument("--mot-csv", default=None, help="the corpus label CSV; ground truth")
    ap.add_argument("--collection", default=None)
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--limit", type=int, default=50, help="results per query")
    ap.add_argument("--mot-limit", type=int, default=None, help="cap rows read from the CSV")
    ap.add_argument("--out", default=None, help="write <out>.json and <out>.md")
    ap.add_argument("--ablations", action="store_true", help="also run the variant sweep")
    ap.add_argument("--save-baseline", default=None)
    ap.add_argument("--check-baseline", default=None)
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="print what would be run and which bands are scorable; touch nothing",
    )
    return ap


def _dry_run() -> int:
    suite = default_suite()
    print(f"{len(suite)} cases\n")
    for case in suite:
        mark = (
            "control" if case.expect_empty else ("scorable" if case.is_scorable else "UNAVAILABLE")
        )
        print(f"  {case.band:14s} {case.id:26s} {mark:12s} {case.query!r}")
    print("\nBands:")
    print(f"  {OBJECT:14s} MOT object counts — exact, independent of the captions")
    print(f"  {COMPOSITIONAL:14s} conjunctions of object predicates — exact")
    print(f"  {BEHAVIOURAL:14s} MOT trajectories through the behaviour rules — exact")
    print(f"  {ATTRIBUTE:14s} UNAVAILABLE — the captions supply both the answer and the truth")
    return 0


async def _run(args: argparse.Namespace) -> int:
    from eval.mot import TracksUnavailable, read_mot_csv, read_mot_tracks
    from search.catalog import get_catalog
    from search.engine import SceneSearchEngine

    if args.host or args.port:
        import os

        from qdrant_client import AsyncQdrantClient

        client = AsyncQdrantClient(
            host=args.host or "127.0.0.1",
            port=args.port or 6333,
            api_key=os.getenv("QDRANT_API_KEY"),
            timeout=60,
        )
        engine = SceneSearchEngine(client=client, collection=args.collection)
    else:
        client = None
        engine = SceneSearchEngine(collection=args.collection)

    catalog = get_catalog()
    await catalog.ensure_loaded(engine._qdrant())  # noqa: SLF001 - the harness is inside the seam
    corpus_videos = {frame.video_id for frame in catalog.frames}
    print(f"Corpus: {len(catalog.frames):,} keyframes across {len(corpus_videos):,} videos")

    suite = default_suite()
    truth_for: dict[str, GroundTruth | None] = {ATTRIBUTE: None}

    if args.mot_csv:
        print(f"Reading ground truth from {args.mot_csv} ...")
        objects = read_mot_csv(args.mot_csv, limit=args.mot_limit, video_ids=corpus_videos)
        print(
            f"  {objects.rows_read:,} rows → {len(objects.counts):,} labelled frames "
            f"across {len(objects.videos):,} videos"
        )
        overlap = objects.videos & corpus_videos
        print(f"  {len(overlap):,} of the index's {len(corpus_videos):,} videos are in the table")
        if not overlap:
            print(
                "\n  The label table and the index share no video ids. Every score would "
                "be zero for that reason alone, so nothing is run.\n"
                f"  index sample: {sorted(corpus_videos)[:3]}\n"
                f"  table sample: {sorted(objects.videos)[:3]}"
            )
            return 2

        mot_truth = MotGroundTruth(truth=objects, predicates=predicates_of(suite))
        truth_for[OBJECT] = mot_truth
        truth_for[COMPOSITIONAL] = mot_truth

        try:
            tracks = read_mot_tracks(args.mot_csv, video_ids=corpus_videos, limit=args.mot_limit)
        except TracksUnavailable as exc:
            print(f"  behavioural band unavailable: {exc}")
            truth_for[BEHAVIOURAL] = None
        else:
            from eval.behavior import detect_behaviors

            events = {
                video_id: detect_behaviors(video_tracks)  # type: ignore[arg-type]
                for video_id, video_tracks in tracks.items()
            }
            total = sum(len(v) for v in events.values())
            print(f"  {total:,} behaviour events across {len(events):,} videos")
            truth_for[BEHAVIOURAL] = BehaviorGroundTruth(
                events_by_video=events,  # type: ignore[arg-type]
                kinds={c.id: c.behavior_kind for c in suite if c.behavior_kind},
            )
    else:
        print("No --mot-csv: every band that needs ground truth will report UNAVAILABLE.")
        truth_for.update({OBJECT: None, COMPOSITIONAL: None, BEHAVIOURAL: None})

    print("\nRunning the suite ...")
    report = await run_suite(
        cast(Engine, engine), truth_for=truth_for, cases=suite, limit=args.limit
    )
    report.corpus_videos = len(corpus_videos)
    report.corpus_keyframes = len(catalog.frames)
    print()
    print(to_markdown(report))

    if args.ablations:
        print("\nRunning ablations ...")
        for name, note, variant in await run_ablations(
            cast(Engine, engine), truth_for=truth_for, cases=suite, limit=args.limit
        ):
            if variant is None:
                print(f"  {name:22s} n/a — {note}")
                continue
            print(f"  {name:22s} P@10 {variant.overall_precision_at_10:.3f}   ({note})")

    if args.out:
        json_path = save_json(report, f"{args.out}.json")
        md_path = save_markdown(report, f"{args.out}.md")
        print(f"\nWrote {json_path} and {md_path}")

    if args.save_baseline:
        path = Path(args.save_baseline)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(to_json(report), indent=2, sort_keys=True), encoding="utf-8")
        print(f"Baseline saved to {path}")

    if args.check_baseline:
        failures = compare_to_baseline(report, args.check_baseline)
        if failures:
            print("\nREGRESSED:")
            for failure in failures:
                print(f"  · {failure}")
            return 1
        print("\nNo regression against the baseline.")

    return 1 if report.controls_failed else 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.dry_run:
        return _dry_run()
    try:
        return asyncio.run(_run(args))
    except FileNotFoundError as exc:
        print(f"{exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - a CLI should not traceback at a user
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
