# SRS — SceneSearch (RAV-14 / P-081)

**Software Requirements Specification**

| Field | Value |
| --- | --- |
| System | SceneSearch — semantic search over recorded driving video |
| Version | 2.0 — 2026-08-21 |
| Status | Production baseline |
| Companions | [MVP.md](MVP.md) (what ships), [adr/](adr/) (locked decisions) |

Every requirement carries an implementation status read from the repository.

| Symbol | Meaning |
| --- | --- |
| ✅ | Implemented and covered by tests |
| 🟡 | Partially implemented — code exists but is not on the live path, or is incomplete |
| ❌ | Not started |

**Shall** = mandatory. **Should** = strong default. **May** = optional.

No retrieval metric, latency figure, or model-throughput number in this document has been measured on a labelled local corpus. Latency figures in [MVP.md](MVP.md) are from attaching to the live Viettech index, not from a formal NFR campaign.

---

## 1. Scope

### 1.1 Purpose

SceneSearch lets an engineer retrieve moments from an archive of recorded driving video using a natural-language description, watch anonymized previews, and export a selected set as a dataset with a JSONL manifest.

### 1.2 System boundary

**In scope:** offline ingestion of recorded video, embedding, anonymization of displayed derivatives, semantic retrieval (visual + caption/structured when present), a browser UI, JWT roles, dataset zip export, and a measurement harness.

**Out of scope, permanently:** any interface that influences a vehicle (NFR-SAFE-01).

**Out of scope for this production cut:** VLM reranking at query time, multi-event sequence queries, SSO, multi-tenancy, a separate `reviewer` role, and HITL approve-before-export on the live API (the review tables remain in Postgres for a later gate).

### 1.3 Definitions

| Term | Meaning |
| --- | --- |
| **Keyframe** | One sampled image from a video, at a timestamp — the retrieval unit |
| **Raw asset** | Original, un-anonymized image or video. Never servable |
| **Derived asset** | Blurred thumbnail or anonymized preview. The only thing displayed |
| **Strict concept** | A named query concept that must be positively confirmed (caption or structured field), not merely left uncontradicted |

---

## 2. Overall description

### 2.1 Deployment topology

Infrastructure runs in Docker. The API and ML worker run **natively on the host** so Metal (MPS) is available (ADR-0001). Search may attach read-only to a remote Qdrant/MinIO index while ingestion still writes local buckets.

```
Browser (React 19 + Vite)
        │  HTTP/JSON  (/api/v1)
┌───────▼─────────────────────────┐
│  FastAPI                        │
│   auth · search · media         │
│   ingest · admin · datasets     │
└───┬──────────┬──────────┬───────┘
    │          │          │
    │      ┌───▼────┐  ┌──▼──────────────┐
    │      │ Redis  │  │ Celery worker   │  native (MPS)
    │      │ broker │  │ pipelines.ingestion
    │      └────────┘  └──┬──────────────┘
    │                     │
┌───▼─────┐  ┌────────────▼──┐  ┌──────────────────────────┐
│ Postgres│  │ Qdrant        │  │ MinIO                    │
│ users   │  │ named vectors │  │ raw (restricted) /       │
│ corpus  │  │ cosine        │  │ derived (proxied)        │
└─────────┘  └───────────────┘  └──────────────────────────┘
```

### 2.2 Technology baseline

| Concern | Choice | Source |
| --- | --- | --- |
| Visual encoder | SigLIP, 768-d, `open-clip-torch` | ADR-0001 |
| Optional visual | Qwen2.5-VL tower when the collection exposes it | `app/ml/qwen_encoder.py` |
| Device | MPS, CPU fallback via `ML_DEVICE` | ADR-0001 |
| Video decode | PyAV | `app/pipelines/ingestion/` |
| Vector store | Qdrant, cosine, named vectors | `app/infrastructure/qdrant.py` |
| Metadata | PostgreSQL + Alembic | `app/db/` |
| Object store | MinIO, two logical buckets | ADR-0003 |
| Broker / status | Redis | `app/infrastructure/redis.py` |
| Task queue | Celery | `app/worker/` |
| Frontend | React 19 + Vite 6 | `frontend/` |

### 2.3 Assumptions

1. The project's own corpus is the Kaggle [*Driving Video with Object Tracking*](https://www.kaggle.com/datasets/robikscube/driving-video-with-object-tracking) set (ADR-0005).
2. The **live read index** currently attached in development is Huy's Viettech collection `Scences` (~29k keyframes / ~918 videos), named vectors `siglip` (768d) and `qwen` (2048d). The spelling `Scences` is the remote name — do not rename it.
3. Many live payloads are caption-sparse. Search is visual-first until VLM captions land; structured fields (people, weather, OCR) are used when present.
4. Attribute-band evaluation ground truth is still independent of captions (FR-EVAL-06). Object/behaviour bands use MOT labels via `app/eval/`.

---

## 3. Functional requirements — Ingestion (`FR-ING`)

| ID | Requirement | Status | Where |
| --- | --- | --- | --- |
| FR-ING-01 | Accept a video upload, return a task id (`202`), expose progress by id. Admin only. | ✅ | `app/api/v1/ingestion.py`, `app/repositories/task_status.py` |
| FR-ING-02 | SHA-256 the source bytes; re-ingestion of identical bytes is a no-op. | ✅ | `pipelines.ingestion` + `repositories/corpus.py` |
| FR-ING-03 | Probe codec, duration, fps, resolution; reject over-limit sources. | ✅ | `pipelines/ingestion/` |
| FR-ING-04 | Decode and sample at `VIDEO_SAMPLE_FPS`. | ✅ | `pipelines/ingestion/sampler.py` |
| FR-ING-05 | Drop near-duplicate frames; fold dropped spans into the keeper. | ✅ | `pipelines/ingestion/deduplicator.py` |
| FR-ING-06 | Embed kept frames with the configured encoder; record `model_version`. | ✅ | `pipelines/ingestion/embedder.py`, `app/ml/encoder.py` |
| FR-ING-07 | Group frames into segments; persist a keyframe per segment. | 🟡 | Segment builder exists; live Viettech index is keyframe-oriented |
| FR-ING-08 | Persist videos, frames, segments to PostgreSQL. | ✅ | `repositories/corpus.py` |
| FR-ING-09 | Upsert points into Qdrant with deterministic ids; support delete-by-`video_id`. | ✅ | `app/search/index.py`, `app/search/points.py` |
| FR-ING-10 | Derive object metadata from MOT track labels; **shall not** run a detector on the ingest critical path. | ❌ | ADR-0002; reader not on the upload path |
| FR-ING-11 | Derive behaviour tags from tracks (image-plane geometry). | 🟡 | `pipelines/ingestion/behavior_detector.py`; `app/eval/behavior.py` for scoring. Not on live search |
| FR-ING-12 | Offline VLM enrichment (weather, time of day, caption) per segment keyframe. | ❌ | Live index captions are Huy's workstream |
| FR-ING-13 | VLM **shall** run per segment keyframe, not per frame. | ❌ | Design rule; see MVP § remaining |
| FR-ING-14 | Ingestion **shall** work when VLM is absent. Semantic search **shall not** require captions. | ✅ | Captionless catalogs search visually |
| FR-ING-15 | Originals in the restricted store; anonymized derivatives in the derived store. | ✅ | ADR-0003; `infrastructure/minio.py` |
| FR-ING-16 | Re-encode a fully anonymized preview clip before the video is playable. | ❌ | Thumbnails exist; full preview MP4 is open |
| FR-ING-17 | Ingest **shall** not depend on a dataset-specific directory layout. | ✅ | Direct upload is the production path |

---

## 4. Functional requirements — Search (`FR-SRCH`)

| ID | Requirement | Status |
| --- | --- | --- |
| FR-SRCH-01 | `POST /api/v1/search` accepts a natural-language query (Vietnamese or English), optional require/exclude, mode, limit, cursor, `explain`. Public (no JWT). | ✅ |
| FR-SRCH-02 | Parse the query into required / excluded concepts behind a length-capped parser. | ✅ |
| FR-SRCH-03 | Inferred constraints are visible to the client (`filters_applied` / confirmed / denied / unconfirmed). Removing a chip widens results. | ✅ |
| FR-SRCH-04 | Attribute constraints resolve from structured payload fields first, then captions. Qdrant `must` filters are for the write-path payload; the live Viettech collection is caption/structured scanned in-process. | ✅ |
| FR-SRCH-05 | Ranking fuses ANN towers with a lexical/caption scan using Reciprocal Rank Fusion. | ✅ | `app/search/fusion.py` |
| FR-SRCH-06 | Each result carries video id, timestamp, score, thumbnail and clip URLs (media is session-gated). One result per video. | ✅ |
| FR-SRCH-07 | `explain=true` includes per-signal breakdown. | ✅ |
| FR-SRCH-08 | Pagination uses an opaque cursor, not an offset. | ✅ | `app/search/cursor.py` |
| FR-SRCH-09 | Text embedding **should** be cached in Redis. | ❌ |
| FR-SRCH-10 | Query encoding **shall** use the same visual encoder configuration as ingestion. | ✅ | `app/ml/encoder.py` |
| FR-SRCH-11 | Optional VLM rerank behind a flag. | ❌ (stretch) |

### 4.1 Behaviour

| ID | Requirement | Status |
| --- | --- | --- |
| FR-BEH-01 … 05 | Ego-path crossing rules, confidence, separate precision/recall from retrieval. | 🟡 | Geometry rules live under `app/eval/behavior.py` for evaluation. Live search does not tag crossings from MOT |

---

## 5. Functional requirements — Privacy (`FR-PRIV`)

| ID | Requirement | Status |
| --- | --- | --- |
| FR-PRIV-01 | Raw store cannot produce a presigned URL; the API has no serve-from-raw path. | ✅ |
| FR-PRIV-02 | Startup fails if raw and derived bucket names are equal; buckets must exist. | ✅ |
| FR-PRIV-03 | Displayed images have face/plate regions blurred. Full preview-clip re-encode is FR-ING-16. | 🟡 |
| FR-PRIV-04 | Anonymization fails closed for frames that cannot be blurred. | ✅ |
| FR-PRIV-05 | Embeddings are computed on the original frame; blur applies only to derivatives. | ✅ | ADR-0003 |
| FR-PRIV-06 | Sample displayed frames and report a measured leak rate. | ❌ |
| FR-PRIV-07 | Blur-region detector is pluggable. | ✅ | `app/ml/anonymize.py` |
| FR-PRIV-08 | Deleting a video cascades DB, Qdrant points, and both object stores. | 🟡 | DB + Qdrant delete-by-video exist; object-store cleanup incomplete |

Media (`GET /api/v1/media/...`) requires a logged-in session (Bearer or cookie `scenesearch_jwt`). Search itself is public.

---

## 6. Functional requirements — Roles (`FR-AUTH`)

Two roles. `reviewer` was removed (Alembic `20260820_0007`).

| ID | Requirement | Status |
| --- | --- | --- |
| FR-AUTH-01 | Roles `engineer` and `admin`. | ✅ | `UserRole` + DB `CHECK` |
| FR-AUTH-02 | `engineer` may search, view media, export dataset zips. `engineer` **shall not** ingest, manage users, or read admin telemetry / eval. | ✅ |
| FR-AUTH-03 | `admin` may do everything an engineer may, plus ingest, user management, telemetry, and eval. | ✅ |
| FR-AUTH-04 | Authorization is enforced server-side (`require_role`). | ✅ | `app/api/deps.py` |
| FR-AUTH-05 | JWT access + refresh, Redis blacklist, bcrypt, `token_version`. | ✅ | `app/services/auth.py` |

Public registration always creates `engineer`. Seed accounts: `scripts/seed_users.py`.

---

## 7. Functional requirements — Review and export (`FR-REV`)

The brief asked for HITL approve-before-export. Postgres still encodes that constraint on `review_sessions` / `datasets`. The **live** export path does not wait on a reviewer.

| ID | Requirement | Status |
| --- | --- | --- |
| FR-REV-01 … 06 | Review session lifecycle, approver ≠ author, export only from `approved`. | 🟡 | Schema ✅; no public review API |
| FR-REV-07 | Export carries query, filters, and provenance. | 🟡 | Live path: `POST /api/v1/datasets/export` returns a zip of selected clips + `manifest.jsonl` (cap 40 unique videos). Drafts live in browser `localStorage` |

---

## 8. Functional requirements — Evaluation (`FR-EVAL`)

| ID | Requirement | Status |
| --- | --- | --- |
| FR-EVAL-01 | Query suite in four bands: attribute, object, compositional, behavioural. | ✅ | `app/eval/` |
| FR-EVAL-02 | Report precision@k, recall, nDCG, MRR, latency. | ✅ | CLI: `make eval` |
| FR-EVAL-03 | Recall denominators use independent truth, not the system's own top-k. | ✅ | MOT / geometry |
| FR-EVAL-04 | Ablations. | 🟡 | Harness supports variants; not all are CI-gated |
| FR-EVAL-05 | CI **may** fail on precision@10 regression (`make eval-check`). | 🟡 | Command exists; not a required GitHub check |
| FR-EVAL-06 | **Shall not** use VLM/caption metadata as ground truth for queries answered by that same metadata. | ✅ | `eval/truth.py::check_independence` |

Attribute band is **unscored** until labels come from outside the caption pipeline (BDD100K attribute JSON joined on video id, or a judged pack). See `app/eval/README.md`.

---

## 9. Non-functional requirements

### 9.1 Performance (`NFR-PERF`)

Design budgets, not a formal campaign. Warm searches against the ~29k-keyframe Viettech catalog have been observed in the 160 ms–2 s range depending on cold catalog/encoder.

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-PERF-01 | Query latency, no rerank, at current catalog size | p50 < 300 ms, p95 < 800 ms (budget) |
| NFR-PERF-04 | Thumbnails via media proxy, never inlined as base64 | ✅ |
| NFR-PERF-06 | SigLIP **shall** apply an absolute similarity floor so out-of-domain queries return empty rather than dashcam neighbours | ✅ | `SEARCH_VISUAL_FLOOR=0.09` (calibrated; see `app/core/config.py`) |

### 9.2 Reliability (`NFR-REL`)

| ID | Requirement | Status |
| --- | --- | --- |
| NFR-REL-01 | Ingestion retries with backoff and reports progress. | ✅ |
| NFR-REL-02 | Task status from Redis with Postgres fallback. | ✅ |
| NFR-REL-03 | Startup verifies Postgres, Redis, Qdrant, MinIO buckets; refuses to start in staging/production on failure. | ✅ |
| NFR-REL-04 | Re-ingesting an already-indexed source is a no-op. | ✅ |

### 9.3 Safety (`NFR-SAFE`)

| ID | Requirement | Status |
| --- | --- | --- |
| NFR-SAFE-01 | No vehicle control interface. | ✅ (by absence) |
| NFR-SAFE-02 | Operates only on recorded data. | ✅ |
| NFR-SAFE-03 | No un-anonymized asset reachable through the API. | ✅ (design) / 🟡 (leak-rate unmeasured) |

### 9.4 Maintainability (`NFR-MAINT`)

| ID | Requirement | Status |
| --- | --- | --- |
| NFR-MAINT-01 | CI runs lint and tests on `main` and `dev`. | ✅ | `.github/workflows/ci.yml` |
| NFR-MAINT-02 | Schema changes go through Alembic. | ✅ |
| NFR-MAINT-03 | `vector_size` is configurable; points carry `model_version`. | ✅ |

---

## 10. Interfaces

### 10.1 REST API

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/health` | public | Liveness |
| `POST` | `/api/v1/search` | public | Retrieval |
| `POST` | `/api/v1/auth/login` | public | JWT pair + cookie |
| `POST` | `/api/v1/auth/register` | public | Creates `engineer` |
| `POST` | `/api/v1/auth/refresh` | public | Rotate tokens |
| `POST` | `/api/v1/auth/logout` | user | Blacklist |
| `GET` | `/api/v1/auth/me` | user | Profile |
| `GET` | `/api/v1/media/thumbnail/{id}` | user | JPEG |
| `GET` | `/api/v1/media/clip/{id}` | user | Byte-range clip |
| `POST` | `/api/v1/ingest/upload` | admin | Queue video |
| `GET` | `/api/v1/tasks/{id}` | admin | Task status |
| `GET` | `/api/v1/admin/telemetry` | admin | Corpus / Qdrant / MinIO / Celery |
| `GET` | `/api/v1/admin/eval` | admin | `reports/eval.json` or `{ available: false }` |
| `POST` | `/api/v1/datasets/export` | engineer or admin | Zip + `manifest.jsonl` |

### 10.2 Vector store

Write path (local ingest): one collection, 768-d cosine, payload from `app/search/points.py`.

Read path (Viettech `Scences`): named vectors `siglip` / `qwen`; payload keys include `video_id`, timestamps, optional caption, OCR, structured lists, MinIO keys. Search adapts; it does not rewrite the remote collection.

### 10.3 Object store

| Store | Contents | Presignable |
| --- | --- | --- |
| `raw` | Originals | **No** |
| `derived` | Thumbnails, previews | Proxied via `/api/v1/media` |

Remote scene media may use MinIO console REST (`MINIO_SCENE_MEDIA_*`) when the hostname is a console, not the S3 API.

### 10.4 Frontend

React 19 client against the live API (Vite proxies `/api` → `:8000`). Routes: `/auth`, `/search`, `/ingestion`, `/admin`, dataset draft/download, eval page. No mock scene list.

---

## 11. Traceability — brief to requirement

| Brief clause | Requirements |
| --- | --- |
| Index a sample dataset | FR-ING-01 … FR-ING-17 |
| NL query → matching moments with preview | FR-SRCH-01, 05, 06; FR-PRIV-03 |
| Filter by metadata | FR-SRCH-03, 04; FR-ING-10, 12 |
| ≥ 2 roles | FR-AUTH-01 … FR-AUTH-05 |
| precision@k report | FR-EVAL-01 … FR-EVAL-06 |
| Hybrid semantic + metadata + behaviour | FR-SRCH-05; FR-BEH (eval) |
| Export dataset from results | FR-REV-07 (zip path) |
| Read-only, no vehicle control | NFR-SAFE-01, NFR-SAFE-02 |
| Anonymize faces/plates in displayed images | FR-PRIV-01 … FR-PRIV-08 |

---

## Sources

- Working tree 2026-08-21 (`chore/production-hygiene` / local `dev` merge of search + ingest)
- [MVP.md](MVP.md), [adr/0001](adr/0001-encoder-and-vector-dimension.md)–[0005](adr/0005-single-corpus-source.md)
- RAV-14 brief
