# ADR-0004: Video tier, indexing granularity, and preview delivery

> **⚠️ SUPERSEDED by [ADR-0005](0005-single-corpus-source.md) (2026-08-09).**
> The corpus is now the single Kaggle *Driving Video with Object Tracking* dataset.
> **Nothing in this document is an instruction.** It is kept because it records why
> the original choice was made and what was lost by changing it. Do not download
> anything named here.


- **Status:** Superseded by ADR-0005
- **Date:** 2026-08-05
- **Milestone:** M0 (extension)
- **Supersedes:** the keyframe-only corpus decision in ADR-0002

## Context

ADR-0002 chose a corpus of BDD100K keyframes: one still per 40-second clip, with
free attribute ground truth, at about 1 GB. That decision was correct for
evaluation and wrong for the product. Video is required in the final deliverable,
for two distinct reasons that were initially conflated:

1. **Indexing.** A single-frame encoder cannot represent motion. The project's
   headline query, *"rainy weather, with a pedestrian crossing in front of the car"*, describes a
   trajectory, not an appearance. Without temporal data the system cannot answer
   it except by proxy.
2. **Delivery.** An engineer triaging driving logs needs to *watch* the moment.
   A still frame with a timestamp is a citation, not a result.

Reverting to BDD100K's video release is not an option: it is roughly 1.8 TB, and
the available disk budget is about 15 GB.

## Decision

### 1. A two-tier corpus

| Tier | Source | Size | Purpose |
| --- | --- | --- | --- |
| **Breadth** | 10,000 BDD100K keyframes (100K Images, val split) | ~0.9 GB | Search volume and free ground truth for precision@k |
| **Depth** | 50-200 BDD100K MOT 2020 val sequences, encoded to MP4 | ~0.3-1.2 GB | Real video: decode, segments, playback, behaviour tracks |

The tiers are not a compromise between two options; they do different jobs. The
breadth tier makes 40 of the 50 evaluation queries answerable with exact ground
truth derived from labels. The depth tier makes the product a video tool and
supplies ground-truth object tracks for the behaviour rules. Neither tier alone
satisfies the brief.

Both tiers use the same schema: a BDD100K keyframe is a `Video` with one `Frame`,
a MOT sequence is a `Video` with about 200. Nothing in retrieval or review
distinguishes them.

### 2. MOT sequences are encoded to MP4 at ingestion time

BDD100K ships its tracking split as directories of JPEG frames, not as video.
`scripts/build_mot_clips.py` encodes each sequence into a single H.264 MP4.

This is a storage *win*, not a cost. A 200-frame sequence of 1280x720 JPEGs is
roughly 18 MB; the same content as H.264 at CRF 28 is closer to 1 MB, a 15-20x
reduction. After conversion the source frames are deleted, because the ingestion
pipeline decodes the MP4 rather than reading the JPEGs. The pipeline is therefore
genuinely video-native: it exercises the same decode path that an uploaded
dashcam file would.

Encoding uses **PyAV**, which bundles its own FFmpeg libraries. No system FFmpeg
install is required on any machine that runs the worker or the converter.

### 3. Two indexing granularities

Every video produces two kinds of Qdrant point, distinguished by the existing
`granularity` payload field:

- **`frame`** - one point per sampled frame. Answers "which instant".
- **`segment`** - one point per span of up to `VIDEO_SEGMENT_SECONDS` (default 5s),
  whose vector is the renormalized mean of its member frame vectors. Answers
  "which few seconds to watch".

Segments exist because a video product must return something playable. Returning
a still from a 40-second clip forces the engineer to hunt for the moment; a
5-second span opens directly on it. Mean-pooling is chosen over a temporal
encoder because it costs nothing extra at index time, requires no additional
model, and is a reasonable approximation when the span is short.

Frame granularity is retained rather than replaced: it is more precise for
appearance queries, and it is what the review and export flow labels.

### 4. Near-duplicate filtering, with span folding

Consecutive frames of driving footage are highly redundant, especially when the
vehicle is stopped. Frames whose cosine similarity to the last kept frame exceeds
`VIDEO_DEDUP_THRESHOLD` (default 0.98) are dropped.

Crucially, a dropped frame's time span is folded into the `covers_start_s` and
`covers_end_s` of the frame that represents it. Deduplication therefore reduces
index cost without creating gaps in time coverage: every second of every clip is
still reachable through some indexed point. Deduplication is configurable and can
be disabled, because the evaluation reports a with/without ablation.

### 5. Playback serves anonymized previews only

The privacy model from ADR-0003 extends to video without modification, and its
cost grows:

- `videos.raw_object_key` is the original clip in the restricted bucket. No
  presigned URL is ever issued for it.
- `videos.preview_object_key` is a **fully anonymized** re-encode in the derived
  bucket. Every frame is blurred before encoding; this is the only video the API
  serves.
- `videos.preview_blurred` mirrors `frames.blurred` and defaults to true, so a
  clip whose anonymization did not complete is never playable.

This is the largest single cost the video requirement adds. Blurring 10,000 still
thumbnails is minutes of work; blurring and re-encoding every frame of 50 clips is
a batch job measured in tens of minutes. It is accepted rather than optimized
because the alternative - blurring on demand at playback - would put a
multi-second delay in front of every result the engineer clicks, and would make
the two-bucket guarantee conditional on request-time code being correct.

## Consequences

- The system is video-native end to end. Accepting an arbitrary uploaded driving
  video requires no new pipeline stage, only relaxing the source validation.
- Index size roughly doubles per video, since segments are indexed alongside
  frames. At this corpus scale that is a few megabytes of vectors and is not a
  meaningful cost.
- Behaviour rules operate on ground-truth MOT tracks, so their measured
  precision and recall reflect the rules themselves, cleanly separated from
  detector error.
- The schedule loses its buffer. The video work is roughly two and a half days
  against a ten-day plan that previously held two days of slack. The descope
  ladder in the delivery plan is now load-bearing rather than precautionary.
- MOT 2020 download links have been reported unreliable. Ingestion is written
  against a manifest rather than a dataset-specific layout, so substituting
  another video source is a converter change, not a pipeline change.

## Alternatives considered

| Option | Why not |
| --- | --- |
| BDD100K video release | ~1.8 TB against a 15 GB budget |
| Keyframes only, with a fake "player" | Dishonest, and does not address the temporal indexing gap |
| Segment granularity only, dropping frames | Loses precision on appearance queries and gives review nothing specific to label |
| Blur previews on demand at playback | Multi-second latency per click, and makes the privacy guarantee depend on request-time code rather than on bucket separation |
| A temporal encoder (VideoCLIP, X-CLIP) | Larger, slower, unnecessary for 5-second spans, and would break the 768-dimension collection |
