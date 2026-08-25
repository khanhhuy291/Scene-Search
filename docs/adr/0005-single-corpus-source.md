# ADR-0005: Single corpus source, with a metadata-only exception for evaluation

- **Status:** Accepted (amended 2026-08-09, same day, before implementation)
- **Date:** 2026-08-09
- **Supersedes:** ADR-0002 (corpus selection), and the corpus half of ADR-0004
- **Milestone:** M1

## Context

ADR-0002 selected a two-tier BDD100K corpus: 10,000 keyframes for breadth plus MOT 2020 sequences encoded to MP4 for video. ADR-0004 built the frame/segment granularity design on top of that tiering.

Three documents and a Makefile were describing three different corpora, which is worse than any one of them being wrong. A developer following `README.md` would have downloaded a registration-gated dataset the team is not using.

The team has settled on one public corpus:

**[Driving Video with Object Tracking](https://www.kaggle.com/datasets/robikscube/driving-video-with-object-tracking)** — video with MOT-format object tracks, no registration.

### Amendment: what changed within the day

This ADR was first written to permit **no** external source of any kind. That was decided while one fact was still unknown: whether the corpus's video identifiers could be joined to any external attribute labels.

Inspection of the label CSV settled it. Filenames follow:

```
01c71072-718028b8-0000001.jpg
└──── video id ────┘└─frame─┘
```

`01c71072-718028b8` is the BDD100K identifier format — two hex groups, hyphen-separated. The join key is present in column 1 of the labels the team already has.

The original decision rested partly on *"it depends on an unverified assumption."* That assumption is now substantially verified, so the trade changed and the decision is amended before any code was written against it.

## Decision

**One corpus: the Kaggle *Driving Video with Object Tracking* dataset.** Every frame, every vector and every displayed asset originates there, and nowhere else.

- No BDD100K imagery or video download. No MOT 2020 frame download.
- No secondary or fallback corpus. nuScenes, KITTI, ZOD and third-party re-uploads remain out of scope.
- Synthetic fixtures from `make fixtures` remain, for plumbing tests only. They are not a corpus and no metric is ever computed on them.

**One narrow exception: a labels-only metadata file may be used as an evaluation ground-truth lookup.** Permitted strictly under all of the following:

| Condition | Why |
| --- | --- |
| It supplies **only** `weather` / `timeofday` / `scene`, joined on video id | Anything more and it becomes a second corpus |
| It is **never ingested, never embedded, never decoded** | It is a lookup table, not source data. It does not enter the pipeline |
| It **never appears in the Qdrant payload** | Search filters come from the enrichment pass, as before. Mixing sources into the payload would make a filter's provenance unknowable |
| It is read **only** by `app/eval/` | One directory, one owner, one reason to exist |
| It is **not required for the product to work** | If it is absent, search, review and export are unaffected. Only the evaluation report narrows |

Indexing granularity is unchanged: frame and ≤5 s segment in one collection, separated by a `granularity` payload field. That half of ADR-0004 stands independently of the tiering.

### Verification gate

The exception is **conditional and time-boxed**. Before the evaluation harness is written, someone confirms that these sequence identifiers actually carry `weather` / `timeofday` / `scene` in the labels release. A matching id *format* is not proof of attribute *coverage* — the tracking sequences and the attribute-bearing release are different distributions of the same project.

- **If coverage is confirmed:** attribute-band ground truth is exact and free. This is the intended path.
- **If it is not:** the exception expires unused, and evaluation reports **object-band metrics only** — queries the track CSV answers exactly, e.g. "scenes with at least 3 pedestrians" — with attribute queries assessed qualitatively and that limitation stated plainly in the report.

**Hand-annotation is explicitly not the fallback.** It was previously listed as an option at roughly one person-day. Against the current schedule — nothing indexed, ingestion still a mock, several components unstarted — a person-day spent labelling is a day taken from making the product work at all. A smaller measured report beats a larger one that did not get finished.

## Consequences

### What this simplifies

**One ingest path.** The corpus ships video with track sidecars, so there is no keyframe tier, no JPEG-sequence-to-MP4 conversion, and no second manifest shape. `scripts/build_mot_clips.py` and `scripts/fetch_bdd100k.py` are no longer part of any supported workflow.

**No registration gate for the corpus.** The download works for anyone, immediately.

**Evaluation keeps its best case without the pipeline taking on any risk.** The exception is quarantined to `app/eval/`. If it fails verification, nothing else changes — no re-index, no schema change, no code thrown away.

### The corpus is far larger than the MVP needs

The label CSV carries roughly 2 million rows at about 9 object rows per frame, so on the order of **220,000 frames across ~1,100 videos** — not the ~50 the MVP targets.

`[Inference]` Derived from a sample of the CSV, not a full count. The order of magnitude is what matters.

**Subsetting happens in the converter, not after ingestion.** The Kaggle CSV → `manifest.jsonl` converter takes a limit and selects N videos; only those clips are ever decoded, embedded, anonymized or stored. Subsetting later would mean paying the largest compute cost in the system — preview anonymization — for clips nobody searches.

Selection should be deterministic (sorted by video id, take the first N) so that two developers with the same limit produce the same corpus, and a re-run is reproducible.

### The circular-evaluation trap still applies

Attribute metadata for **search** comes from the offline vision-language enrichment pass. If that same pass also supplied the **ground truth** for attribute queries, precision@k would measure the model agreeing with itself and return a high number that means nothing.

The exception above exists precisely to avoid that: ground truth from an independent source, searchable metadata from the enrichment pass. If the exception expires unused, the object band is the only place where ground truth is genuinely independent — which is why it becomes the whole report rather than part of it.

### What has to change in the code

Not done by this ADR; recorded so it is not lost.

| Item | Owner | Note |
| --- | --- | --- |
| Kaggle CSV → `manifest.jsonl` converter, with a video limit | A | Does not exist. **Ingestion cannot run without it.** Must stream and group by video id — 2M rows should not be loaded whole |
| `make dataset` / `make clips` | A | Implement the superseded BDD100K path. Retarget or remove |
| `scripts/fetch_bdd100k.py`, `scripts/build_mot_clips.py` | A | No longer a supported workflow |
| `DATASET_ROOT` default `data/bdd100k` | D | Stale default in `app/core/config.py` |
| Attribute-coverage verification, then the eval harness | D | The gate above. Before the harness, not during |

Ingestion itself needs no change: it consumes `manifest.jsonl`, never a dataset layout, which is exactly why swapping corpora is a converter change rather than a pipeline change.

## Alternatives considered

**Permit no external source at all.** This was the first version of this ADR, and it was reversed the same day. The argument for it was coordination cost: a second source has to be documented, kept in step, and re-verified. That argument is sound in general and weak here, because the exception as scoped touches exactly one directory, is read-only, and cannot affect the product if it is absent.

Worth recording for anyone reading this later: **it was never rejected on size.** The 1.8 TB figure that ruled out BDD100K belongs to its *video* release, which this project never wanted. The labels release is roughly 100 MB and is never decoded, embedded or ingested. No team member's device constraint has any bearing on a 100 MB metadata file.

**Hand-annotate the attribute band.** Roughly one person-day for two annotators over ~10 queries' worth of pooled candidates, reporting Cohen's κ. Rejected as a fallback on schedule grounds — see the verification gate. It remains available if the team later finds it has the time and wants attribute metrics badly enough.

**Use a pre-made 50-video subset published by another uploader.** Rejected. A second source is a second thing to keep in step, and the converter can subset deterministically in one pass.

**Keep the two-tier design.** Rejected with ADR-0002. The corpus ships video with tracks; a keyframe tier adds a second ingest path for no benefit.

## References

- [Driving Video with Object Tracking — Kaggle](https://www.kaggle.com/datasets/robikscube/driving-video-with-object-tracking) — the project's only corpus
- ADR-0002 (superseded), ADR-0004 (corpus half superseded; granularity stands)
- `docs/MVP.md` — current corpus and evaluation ground-truth rules
