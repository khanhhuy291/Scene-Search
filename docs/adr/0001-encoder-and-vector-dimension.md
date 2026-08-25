# ADR-0001: Vision-text encoder and vector dimension

- **Status:** Accepted
- **Date:** 2026-08-05
- **Milestone:** M0

## Context

SceneSearch retrieves driving keyframes from natural-language queries, so it needs a
shared image-text embedding space. Two constraints shape the choice:

1. `QdrantSettings.vector_size` was pinned to `Literal[768]`, and the `scenes` collection
   is created with that size. Any encoder producing a different dimension would require a
   settings change *and* a collection rebuild.
2. Embedding runs on an Apple M4 Pro through the PyTorch MPS backend, not CUDA. Throughput
   is adequate but not unlimited, and MPS has known gaps in fp16 numerics for some
   operators.

## Decision

**Encoder:** `ViT-B-16-SigLIP` (WebLI weights) at 224 px, loaded through `open-clip-torch`,
which is already declared in the `[ml]` optional dependencies.

- Output dimension is 768, matching the existing collection.
- SigLIP's sigmoid loss outperforms CLIP's softmax contrastive loss at comparable size on
  retrieval benchmarks.
- 224 px means 196 patches per image versus 576 at 384 px — roughly 3x cheaper per frame on
  MPS for a modest quality cost. At a 10,000-frame corpus this is the difference between a
  ~3 minute and a ~10 minute index pass, which matters when re-indexing during development.

**Device:** MPS with fp32, with a `cpu` escape hatch via `SCENESEARCH_ML_DEVICE`.
fp32 is chosen over fp16 because MPS fp16 has produced numerical anomalies in some
transformer operators, and at this corpus size fp32 is fast enough that the risk is not
worth taking.

**Dimension pinning is removed.** `QdrantSettings.vector_size` becomes a plain `int`
(bounded 64..4096), and every Qdrant point carries a `model_version` payload field.

**The ML extra pins `transformers` and `sentencepiece` explicitly.** This is not
incidental packaging. `ViT-B-16-SigLIP`'s open_clip config declares
`"hf_tokenizer_name": "timm/ViT-B-16-SigLIP"`, so the text tower tokenizes through
HuggingFace `transformers` — but `open-clip-torch` declares `transformers` only
under its optional `training` extra. On a default install, image embedding works
and text embedding raises `ImportError`.

That failure mode is unusually nasty: ingestion would appear completely healthy
while search could not encode a query at all, and it would surface days later
during the retrieval milestone rather than at install time. `scripts/benchmark_encoder.py`
therefore exercises `encode_text` as well as `encode_image`, so the day-2
throughput gate also functions as a dependency gate.

### Verification

Checked against open_clip 3.3.0's own `model_configs/*.json` rather than assumed:

| Model | `embed_dim` | `image_size` |
| --- | --- | --- |
| `ViT-B-16-SigLIP` (chosen) | **768** | **224** |
| `ViT-B-16-SigLIP-256/384/512` | 768 | 256 / 384 / 512 |
| `ViT-L-16-SigLIP-256/384` | 1024 | 256 / 384 |
| `ViT-SO400M-14-SigLIP(-384)` | 1152 | 224 / 384 |

The startup guard in `Settings.encoder_dimension_must_match_collection` hardcodes
this table; `test_known_dimensions_match_open_clip_configs` re-derives it from the
installed open_clip so upstream changes cannot silently invalidate the guard.

## Consequences

- Swapping to a stronger encoder later (for example `ViT-SO400M-14-SigLIP-384` at 1152-d)
  becomes a configuration change plus a re-index, not a code and schema migration. At
  10,000 frames a full re-index is a few minutes, so this is cheap.
- `model_version` in the payload allows two encoders to coexist in one collection during a
  migration, filtered apart at query time. Without it, a mid-migration collection returns
  silently wrong results because cosine distance between two different embedding spaces is
  meaningless but still numerically valid.
- Collection compatibility validation in `infrastructure/qdrant.py` must compare against the
  configured size rather than a hardcoded constant.
- Upgrading to the 384 px variant remains available if the day-2 benchmark shows headroom;
  it is the same 768 dimensions, so it needs no schema change at all.

## Alternatives considered

| Option | Why not |
| --- | --- |
| OpenAI CLIP ViT-L/14 | Also 768-d, but weaker than SigLIP on retrieval and ~4x the compute |
| SigLIP so400m (1152-d) | Best quality, but breaks the pinned dimension and is ~5x slower on MPS |
| SigLIP ViT-B-16 @ 384 | Same 768-d and better quality; held as an upgrade if benchmarks allow |
| Video encoders (VideoCLIP, X-CLIP) | Corpus is single keyframes per clip; no temporal input to exploit |
