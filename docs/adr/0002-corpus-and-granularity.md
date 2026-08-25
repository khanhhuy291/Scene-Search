# ADR-0002: Corpus selection and indexing granularity

> **⚠️ SUPERSEDED by [ADR-0005](0005-single-corpus-source.md) (2026-08-09).**
> The corpus is now the single Kaggle *Driving Video with Object Tracking* dataset.
> **Nothing in this document is an instruction.** It is kept because it records why
> the original choice was made and what was lost by changing it. Do not download
> anything named here.


- **Status:** Superseded by ADR-0005
- **Date:** 2026-08-05
- **Milestone:** M0

## Context

RAV-14 requires a searchable driving-data corpus, a `precision@k` quality report, and
delivery within two weeks on a laptop with constrained disk. Three requirements pull
against each other:

- A meaningful `precision@k` needs relevance ground truth.
- Hand-annotating ground truth for a driving corpus costs days.
- Full-resolution driving video is measured in hundreds of gigabytes to terabytes.

## Decision

**Corpus: BDD100K "100K Images", validation split.** 10,000 keyframes, one per 40-second
clip, extracted at the 10-second mark, plus the `det_20` detection labels and per-image
attributes.

The decisive property is that BDD100K labels `weather`, `timeofday`, and `scene` per image
and ships 2D boxes for 10 object classes. This converts the `precision@k` requirement from
a multi-day annotation exercise into a database query, because the relevance set for
"night driving in the rain" is exactly the set of images labeled `weather=rainy` and
`timeofday=night`.

**Video files are not downloaded.** BDD100K's video release is roughly 1.8 TB and adds
nothing: the labels are attached to the keyframes, not the video. Working set is about
1.4 GB.

**Optional temporal corpus:** 30 sequences from the BDD100K MOT 2020 validation split
(~6,000 frames, ~0.5 GB) with ground-truth object tracks, used only for the behavior rules
in M5.

**Object metadata comes from ground-truth labels, not from running a detector.** Running
YOLO to re-derive boxes that the dataset already provides would add an inference pass, a
model dependency, and a source of error to the critical path, in exchange for nothing. A
detector interface is retained for non-BDD corpora and for anonymization (see ADR-0003).

**Granularity: one Qdrant point per frame.** A BDD100K keyframe is modeled as a `video` row
with exactly one `frame` row; a MOT sequence is a `video` with roughly 200 `frames`. One
schema serves both, and adding real video decoding later changes only the ingestion stage.

## Consequences

- 40 of the 50 evaluation queries (attribute, object, and compositional bands) get exact
  ground truth for free. Only the ~10 behavioral queries need manual annotation, and that
  band is first on the descope ladder.
- The entire video decode and adaptive sampling stage disappears from the schedule. This is
  the single largest time saving in the plan.
- Near-duplicate filtering becomes irrelevant for the primary corpus, since keyframes are
  one-per-clip and already distinct. It remains applicable to the MOT subset.
- Single-keyframe indexing cannot represent motion. Queries such as "pedestrian crossing in
  front of the car" are not answerable by the encoder alone; they are served by behavior
  tags derived from MOT tracks. This is the project's principal technical risk and is
  tracked as such.
- Results are limited to BDD100K's label vocabulary for filtering. Semantic search is not
  limited this way, only the structured filters are.

## Alternatives considered

| Option | Why not |
| --- | --- |
| nuScenes | Excellent temporal and ego-pose data, but 30+ GB minimum and no free relevance labels for text queries |
| Zenseact ODD / ZOD | Similar size and setup burden; devkit learning curve does not fit two weeks |
| KITTI | Small but old, narrow scene diversity, weak attribute labeling |
| BDD100K full video release | ~1.8 TB; provides nothing the keyframes and MOT subset do not |
| BDD100K train split (70k images) | 7x the index time and disk for no additional evaluation value at prototype scale |
