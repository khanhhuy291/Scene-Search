# ADR-0003: Anonymization policy for displayed frames

- **Status:** Accepted
- **Date:** 2026-08-05
- **Milestone:** M0

## Context

The RAV-14 constraint requires anonymizing faces and license plates in displayed images.
faces and license plates **in displayed images**.

This leaves one genuinely consequential question open: are embeddings computed on the
original frame or on the blurred one? The answer determines retrieval quality on
person-centric queries and cannot be changed later without a full re-index.

## Decision

### 1. Embed the original, display the blurred

Embeddings are computed from the unmodified frame. Blurring is applied only when producing
the derivative assets that reach a browser.

Rationale: blurring destroys exactly the pixels that a person-centric query depends on.
Embedding blurred frames would degrade queries such as "pedestrian crossing the road" while
delivering no privacy benefit that the display-time blur does not already provide, because
the vector is never rendered and is not reversible into a recognizable face.

This matches the constraint as written. If a stricter reading is later required, originals
are retained and a re-index takes minutes at this corpus size. The precision delta should
be measured before switching, not assumed.

### 2. Two buckets, structurally separated

| Bucket | Contents | Access |
| --- | --- | --- |
| `scenesearch-raw` | Original keyframes | Service account only. No presigned URL is ever issued. |
| `scenesearch-derived` | Blurred thumbnails and previews | Short-TTL presigned URLs |

The API has no code path that serves from `raw`. This is enforced by construction rather
than by policy: the asset endpoint accepts a derived-bucket key only.

### 3. Pluggable blur-region detection, with a stated prototype default

`BlurRegionDetector` is an interface. Two implementations:

- **`LabelHeuristicDetector` (default for the 2-week build).** Derives regions from the
  the corpus's ground-truth boxes already present: the upper 40% of each `person` and `rider`
  box (head region) and the lower-center 35% of each `car`, `truck`, and `bus` box (plate
  region), dilated 10%.
- **`ModelDetector` (drop-in upgrade).** A dedicated face and plate model such as
  YOLOv8n-face, behind the same interface.

The heuristic is prototype-grade and is documented as such. It deliberately over-blurs:
it blurs heads that are turned away and vehicle regions with no visible plate. Over-blurring
is the correct direction to fail in, and it avoids putting an unvalidated third-party weight
download on the critical path of a two-week schedule.

### 4. Fail closed

`frames.blurred` is `NOT NULL DEFAULT true`. A frame whose anonymization step fails is
marked `false` and is excluded from every display path. A frame is never shown because
anonymization was skipped.

### 5. Measure, do not claim

Every ingest batch samples 200 frames, runs an independent detector pass over the blurred
output, and records a leak rate. Target is zero detections above 0.5 confidence. The
measured number is published in the evaluation report. No claim of perfect anonymization
is made.

## Consequences

- Retrieval quality on person queries is preserved.
- The privacy guarantee rests on bucket separation, which is auditable, rather than on
  detector recall, which is not.
- Swapping in a real face and plate model changes one config value and requires
  regenerating thumbnails only, not re-embedding.
- Because blurring only affects derivatives, thumbnail regeneration is independent of the
  vector index; the two can be re-run separately.
- A future policy flip to embed-blurred is a re-index, not a redesign.
