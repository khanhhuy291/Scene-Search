# Retrieval evaluation

Measures search quality against ground truth that was **not** produced by the
system being measured.

```
make eval-dry                                   # what would run, and what is scorable
make eval mot=../data/mot_labels.csv            # the real numbers (needs the index)
make eval-check mot=../data/mot_labels.csv      # CI: fail on regression
python -m pytest tests/unit/test_eval_*.py      # the harness itself, no index needed
```

## What each band can be scored against

| Band | Ground truth | Status |
| --- | --- | --- |
| **object** | MOT label table — object counts per frame | Exact. The table lists every labelled object in every labelled frame, so the recall denominator is the true one, not a pooled estimate |
| **compositional** | conjunctions of object predicates | Exact, for the conjunctions whose halves are both object-backed |
| **behavioural** | MOT trajectories through `eval.behavior` | Exact, and independent: the rules read box geometry, never captions |
| **attribute** | none | **UNAVAILABLE** — and left that way deliberately |

### Why the attribute band is not scored

The weather and time-of-day the search matches on come from the captions. So do
any labels we could derive for those queries. Scoring one against the other
measures the captioner agreeing with itself and produces a number near 1.0 —
which would be the highest figure in the report and the first one anyone quotes.

`eval/truth.py::check_independence` refuses the combination in code rather than
in a comment, because the violation is invisible in the output. SRS FR-EVAL-06.

To make the band scorable, get labels from outside the caption pipeline: the
BDD100K attribute JSON joined on video id, or a judging pack filled in by two
people with Cohen's κ reported.

## What the numbers mean

**precision@k divides by k**, so it is comparable to published figures. That
punishes correct abstention — three results, all right, scores P@10 = 0.3 — so
`precision_of_shown` is reported alongside it. Read them together, or the
similarity floor looks like a regression.

**Relevance is judged on the keyframe that was shown**, not on the video. A video
that contains a qualifying frame somewhere but was represented by a keyframe that
does not qualify is a miss, because what the user clicks is wrong. The report's
*"Right video, wrong moment"* section separates those two failures — one is a
retrieval problem, the other is keyframe selection.

**NaN is not zero.** A missing measurement is reported as absent, never averaged
in as a bad score.

## The join is the thing most likely to be wrong

Label rows are named `01c71072-718028b8-0000001.jpg`; the index keys on
`video_id` and `frame_no`. If those identifier spaces do not line up, every
lookup misses, every score is zero, and the report reads as catastrophic
retrieval instead of a broken join.

The harness reports the join rate above every metric and refuses to run at all
when the two id sets do not intersect. Check that line first, always.

## The regression gate

`make eval-check` compares precision@10 per band against
`eval/baselines/live.json` and fails on a relative drop of more than 5%
(FR-EVAL-05). Two additional failure conditions:

- **A band that becomes UNAVAILABLE fails.** Losing the ability to measure
  something is a regression, and it is the one most likely to arrive by accident —
  a renamed payload field, a label file that stopped being mounted.
- **A failed abstention control fails outright**, no tolerance. A query with no
  possible answer returning results is worse for a user than a few points of
  precision.

Record a baseline only once the numbers are trusted:

```
python -m eval.cli --mot-csv ../data/mot_labels.csv --save-baseline eval/baselines/live.json
```

## Ablations

`--ablations` runs the variants that exist: the two towers separately, strict
concepts off, floor off. The variants named in FR-EVAL-04 that this system does
not have — prompt expansion, reranking, frame vs segment — are listed in the
output as not applicable with the reason, rather than omitted, so an absent row
cannot be mistaken for a zero.

## Files

| File | |
| --- | --- |
| `metrics.py` | precision@k, recall@k, nDCG@k, MRR, percentiles. Pure functions |
| `mot.py` | streams the label CSV into per-frame counts and trajectories |
| `truth.py` | ground-truth sources and the circularity guard |
| `suite.py` | the committed query suite, four bands plus abstention controls |
| `runner.py` | runs a suite, refuses what it cannot measure |
| `report.py` | markdown, JSON, and the CI gate |
| `cli.py` | `python -m eval.cli` |
