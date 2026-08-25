# SceneSearch-P-081

SceneSearch indexes driving video into searchable scenes. Upload a clip, anonymize faces and plates, embed with SigLIP, store derivatives in MinIO, and retrieve by natural language against Qdrant.

The live product includes JWT auth, admin telemetry, dataset zip export, and optional attach to a remote Viettech Qdrant/MinIO index. Product requirements: [docs/SRS.md](docs/SRS.md) and [docs/MVP.md](docs/MVP.md). Corpus policy is ADR-0005: one driving-video dataset, not BDD100K.

## Architecture

```text
Browser (localhost:5173)
  |
  | POST /api/v1/ingest/upload     POST /api/v1/search
  v
FastAPI  ---- task status ----> Redis + PostgreSQL
  |
  | enqueue video_id
  v
Celery worker
  |-- acquire from MinIO raw
  |-- decode, sample, anonymize
  |-- SigLIP embed
  |-- store derivatives in MinIO
  |-- upsert vectors in Qdrant
  '-- update task status
```

| Service | Responsibility | Default address |
| --- | --- | --- |
| Frontend | React 19 search, ingest, auth, admin | http://localhost:5173 |
| API | Auth, search, media proxy, ingest enqueue | http://localhost:8000 |
| Worker | Ingestion pipeline (`pipelines.ingestion`) | Internal |
| PostgreSQL | Users, corpus, task records | localhost:5432 |
| Redis | Status cache, Celery broker and results | localhost:6379 |
| MinIO | Raw originals + anonymized derivatives | http://localhost:9001 |
| Qdrant | Scene vectors | http://localhost:6333/dashboard |

On macOS, run only backing services in Docker (`make docker-infra`) and the API/worker on the host so Metal (MPS) is available (ADR-0001).

## Project structure

```text
SceneSearch-P-081/
|-- app/
|   |-- api/main.py                 FastAPI app and startup checks
|   |-- api/v1/                     auth, search, ingest, media, admin, datasets
|   |-- core/                       settings, logging, JWT
|   |-- db/                         SQLAlchemy models and Alembic
|   |-- infrastructure/             Postgres, Redis, MinIO, Qdrant
|   |-- pipelines/ingestion/        production ingest stages
|   |-- worker/                     Celery app and ingest task
|   |-- search/                     retrieve, catalog, write path
|   |-- services/                   auth, admin, dataset export
|   |-- ml/                         SigLIP / caption encoders, anonymize
|   |-- eval/                       retrieval evaluation harness
|   |-- tests/                      unit, api, integration
|-- frontend/                       React + Vite UI
|-- docker-compose.yml              local stack
|-- docker-compose.deploy.yml       full production stack
|-- docs/                           SRS, MVP, ADRs
|-- Makefile
'-- README.md
```

The backend is a flat package under `app/`. Run Python from `app/`, or use the root Makefile.

## Prerequisites

Docker Engine or Desktop, Compose v2, GNU Make. For host-native apps: Python 3.11+, Node.js 20+, npm.

## Docker quick start

```bash
cp app/.env.example app/.env
make docker-up
```

The API container applies Alembic migrations before Uvicorn starts.

```bash
docker compose --env-file app/.env ps
curl http://localhost:8000/health
```

- Frontend: http://localhost:5173
- API docs: http://localhost:8000/docs
- MinIO console: http://localhost:9001
- Qdrant dashboard: http://localhost:6333/dashboard

```bash
make docker-down
docker compose --env-file app/.env down --volumes   # destroys local data
```

Preferred on a Mac:

```bash
make docker-infra
make install
make migrate
make backend    # terminal 1
make worker     # terminal 2
make frontend   # terminal 3
```

`make install-ml` is required on the host if you will encode queries or ingest video.

## Configuration

Settings come from the process environment and `app/.env`. Never commit `app/.env`.

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | `development`, `test`, `staging`, or `production` |
| `DATABASE_URL` | Async PostgreSQL URL |
| `REDIS_URL` / `CELERY_*` | Status cache and Celery |
| `MINIO_ENDPOINT` | Host:port, no scheme |
| `MINIO_RAW_BUCKET` / `MINIO_DERIVED_BUCKET` | Must differ (ADR-0003) |
| `QDRANT_HOST` or `QDRANT_URL` | Local or remote index |
| `QDRANT_COLLECTION` | Write path defaults to `scenes`. The Viettech read index is `Scences` — do not "fix" the spelling |
| `AUTH_SECRET_KEY` | JWT signing secret |

Compose overrides hostnames so containers talk on the internal network. Remote attach (`QDRANT_URL`, `MINIO_SCENE_MEDIA_*`) is documented in `app/.env.example`. The live Viettech collection name is `Scences` — do not rename it. `QDRANT_URL` must include `:443`.

Seed demo users after migrate: `cd app && .venv/bin/python ../scripts/seed_users.py`. Search is public; thumbnails and clips need a logged-in session.

## API

Routes live under `/api/v1` except `GET /health`. Ingest and admin require an authenticated admin. Search is public. Media requires a logged-in session.

```bash
curl http://localhost:8000/health
# POST /api/v1/auth/login
# POST /api/v1/search            {"query": "rainy day without pedestrians"}
# POST /api/v1/ingest/upload     multipart video, admin only
# GET  /api/v1/tasks/{id}
```

## Database migrations

```bash
make migrate
make migration name=describe_change
```

Compose runs migrations on API startup for local convenience. Staging and production should run them as a separate release step.

## Quality

```bash
make lock
make lint
make test
make quality    # lint + test + frontend build
```

CI runs backend ruff + pytest (`.[dev,media]`), frontend lint/test/build, and production Compose validation on pull requests and pushes to `main` and `dev`. A successful push to `main` deploys the exact tested commit through the protected `production` GitHub Environment; see [deploy/README.md](deploy/README.md).

Tests: `app/tests/unit/`, `app/tests/api/`, `app/tests/integration/`.

## Documents

| Doc | Role |
| --- | --- |
| [docs/SRS.md](docs/SRS.md) | Requirements and current status |
| [docs/MVP.md](docs/MVP.md) | What ships, acceptance test, remaining work |
| [docs/adr/](docs/adr/) | Encoder, corpus, privacy, granularity |

## Development conventions

- HTTP contracts in `schemas/`. Handlers stay thin; workflows live in `services/`, `repositories/`, or `pipelines/`.
- External systems only through `infrastructure/` adapters.
- Alembic for every schema change.
- Blocking SDKs go to a worker thread from async API paths.
- Celery tasks must be idempotent.
- Never commit secrets, generated media, local data, or model weights.

## Troubleshooting

Backend environment missing: `make install`.

Port in use: the stack uses 5173, 5432, 6379, 6333, 6334, 8000, 9000, and 9001.

```bash
docker compose --env-file app/.env ps
docker compose --env-file app/.env logs postgres redis minio qdrant
```

Host-native API/worker must use `localhost`, not Compose service names.

Tasks stuck queued: confirm a worker is consuming the `ingestion` queue (`make worker`).
