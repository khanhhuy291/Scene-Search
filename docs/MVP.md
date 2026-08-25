# MVP — SceneSearch (P-081)

What the production cut is, how to accept it, and what is still open.

Companion: [SRS.md](SRS.md) (normative requirements), [adr/](adr/) (locked decisions). How to run the stack: root [README.md](../README.md).

---

## 1. In one sentence

An engineer types a description of a driving situation, gets ranked watchable moments (faces and plates blurred on derivatives), and exports selected clips as a zip with a JSONL manifest. Two roles (`engineer`, `admin`) are enforced on the API.

---

## 2. What is in / out

### In

| Area | Production content |
| --- | --- |
| **Search** | Public `POST /api/v1/search`. SigLIP (+ Qwen when present), caption/structured scan, RRF, per-keyframe exclusions, one card per video, cursor pagination, similarity floor |
| **Corpus (read)** | Attach to Viettech `Scences` (~29k keyframes / ~918 videos) or a local Qdrant filled by ingest |
| **Ingest** | Admin upload → Celery → `pipelines.ingestion` → MinIO + Postgres + Qdrant |
| **UI** | Search, auth, ingest jobs, admin telemetry, dataset draft/download, eval page (honest empty if no report) |
| **Roles** | `engineer` and `admin`. Media and export need a session; search does not |
| **Export** | Zip of selected clips + `manifest.jsonl` (not a stub) |
| **Eval** | `make eval` / `app/eval/` — object and behaviour bands from MOT; attribute band refused if it would score captions against themselves |

### Out (this cut)

- Separate `reviewer` role and approve-before-export API (schema still has the tables)
- MOT-driven object/behaviour **ingest** on the upload path
- Full anonymized preview MP4 re-encode (FR-ING-16)
- VLM caption enrichment of the live index (Huy's workstream — do not add a second pipeline)
- Query-time VLM rerank, SSO, multi-tenancy
- Attribute-band precision@k until independent labels exist

---

## 3. Acceptance test

Run unrehearsed on a machine attached to infra (`make docker-infra`) and, for a populated grid, the remote index in `app/.env`.

1. Open `/search` **signed out**. Query `rainy day without people` (or `trời mưa, không có người đi bộ`). Results return; inferred constraints are visible; clearing an exclusion widens the set.
2. Out-of-domain query (`spiderman`) returns **empty**, not dashcam neighbours.
3. Log in as engineer (`scripts/seed_users.py`). Thumbnails and clips load; the player **seeks to the matched moment**.
4. Confirm a thumbnail/clip URL **401s** when logged out.
5. Log in as admin. Upload a short clip via `/ingestion`. Task progress moves off queued only if `make worker` is running.
6. As engineer or admin, select results and **download a zip** with `manifest.jsonl`.
7. Admin eval page shows a real `reports/eval.json` or `{ available: false }` — never fabricated scores.
8. Raw MinIO objects are not reachable through `/api/v1/media`.

Steps 2, 3, 4, and 8 are the brief's privacy / honesty constraints. They are not optional.

---

## 4. Architecture in brief

Native API + worker (MPS). Docker only for Postgres, Redis, MinIO, Qdrant.

- **Write path:** upload → checksum → decode/sample → embed → anonymize thumbs → Postgres → Qdrant (`search/index.py`).
- **Read path:** catalog snapshot of payloads + ANN on named vectors. Completeness for lexicon concepts comes from the caption/structured scan, not from ANN alone.
- **Captionless catalogs** do not silently drop the caller's `strict_concepts` flag for frames that *have* captions; visual exclusions still apply when the whole catalog has no captions.

Corpus policy: **one** driving-video source (ADR-0005). Do not ingest BDD100K imagery. A labels-only file may be used by `app/eval/` as ground truth and must never be written into Qdrant.

---

## 5. Remaining work (not “the app is a mock”)

| Item | Owner shape | Notes |
| --- | --- | --- |
| VLM captions on `Scences` | Huy | Search stays visual-first until they exist |
| MOT reader + behaviour on **ingest** | Ingest | Eval already scores behaviour from MOT geometry |
| Anonymized preview MP4 | Ingest | Thumbnails already fail closed |
| Dataset drafts in Postgres | Platform | Downloads are real; the selection list is `localStorage` |
| Attribute eval labels | Eval | Join BDD100K attributes on video id, or a judged pack |
| GitHub Actions minutes | Org billing | CI workflow exists; jobs no-op if the org spending limit is $0 |

---

## 6. What “good” looks like

Targets, not promises.

| Metric | Target |
| --- | --- |
| precision@5 / @10 (object band, MOT truth) | ≥ 0.80 / ≥ 0.70 |
| recall@50 | ≥ 0.75 |
| Query latency p50 / p95 | < 300 ms / < 800 ms |
| Anonymization leak rate | 0 detections above 0.5 confidence (unmeasured) |

A measured miss with an explanation is better than a target quietly dropped.

---

## 7. Demo accounts

Idempotent seed: `cd app && .venv/bin/python ../scripts/seed_users.py`

| Email | Role |
| --- | --- |
| `admin@scenesearch.ai` | admin |
| `engineer@scenesearch.ai` | engineer |

Passwords are in the seed script, not in this document.
