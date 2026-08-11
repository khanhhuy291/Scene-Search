# SceneSearch-P-081

SceneSearch is a monorepo for multimodal video-scene indexing and semantic search. It combines a FastAPI API, Celery workers, PostgreSQL, Redis, MinIO, Qdrant, and a React frontend.

> **Current status:** foundation/scaffolding phase. Configuration, infrastructure clients, task tracking, migrations, local orchestration, tests, and CI are established. Video decoding, real embeddings, vector indexing, semantic retrieval, and the product UI are planned for the next phase.

## Contents

- Architecture
- Project structure
- Prerequisites
- Docker quick start
- Local development
- Configuration
- API guide
- Database migrations
- Dependencies and quality checks
- Development conventions
- Troubleshooting
- Next-phase plan

## Architecture

The intended ingestion flow is:

~~~text
Client
  |
  | POST /api/v1/ingest
  v
FastAPI ---- creates task status ----> Redis + PostgreSQL
  |
  | enqueue
  v
Celery worker
  |-- acquire and validate video
  |-- decode and sample frames
  |-- generate scene embeddings
  |-- store assets in MinIO
  |-- index vectors and metadata in Qdrant
  '-- update task status
~~~

The current worker exercises queueing, progress reporting, retry behavior, and completion with deterministic mock frame and embedding data. This keeps the setup testable before the ML pipeline is introduced.

| Service | Responsibility | Default address |
| --- | --- | --- |
| Frontend | React application and future search UI | http://localhost:5173 |
| API | Validation, lifecycle, and task submission | http://localhost:8000 |
| Worker | Long-running ingestion work | Internal |
| PostgreSQL | Durable task and future scene metadata | localhost:5432 |
| Redis | Status cache, Celery broker, and results | localhost:6379 |
| MinIO | Video, thumbnail, and derived assets | http://localhost:9001 |
| Qdrant | Scene vectors and similarity search | http://localhost:6333/dashboard |

## Project structure

~~~text
SceneSearch-P-081/
|-- app/                              # Python backend
|   |-- main.py                       # Uvicorn compatibility entry point
|   |-- api/
|   |   |-- main.py                   # FastAPI app and lifecycle
|   |   |-- routes.py                 # Agent scaffold routes
|   |   '-- v1/ingestion.py           # Ingestion and task endpoints
|   |-- agents/
|   |   |-- graph.py                  # LangGraph construction
|   |   |-- state.py                  # Shared graph state
|   |   |-- nodes/                    # Agent processing nodes
|   |   '-- tools/                    # Agent tools and search scaffold
|   |-- core/
|   |   |-- config.py                 # Typed environment settings
|   |   '-- logging.py                # Structured logging
|   |-- infrastructure/
|   |   |-- postgres.py               # Async engine and sessions
|   |   |-- redis.py                  # Async pool and client
|   |   |-- minio.py                  # Object-storage adapter
|   |   '-- qdrant.py                 # Vector client and collection setup
|   |-- repositories/task_status.py   # Redis/PostgreSQL task persistence
|   |-- schemas/                      # Pydantic API contracts
|   |-- worker/
|   |   |-- celery_app.py             # Celery configuration
|   |   |-- tasks/ingestion.py        # Ingestion task scaffold
|   |   '-- pipelines/                # Future processing pipeline
|   |-- db/
|   |   |-- models/                   # Future SQLAlchemy models
|   |   '-- migrations/               # Alembic environment and revisions
|   |-- ml/                           # Future model inference
|   |-- search/                       # Future indexing and retrieval
|   |-- services/                     # Application integrations
|   |-- tests/                        # Unit, API, integration, and E2E tests
|   |-- docker/                       # Service initialization
|   |-- scripts/                      # Developer utilities
|   |-- pyproject.toml                # Package and tool configuration
|   |-- requirements.lock             # Resolved dependencies
|   |-- alembic.ini                   # Migration configuration
|   |-- Dockerfile
|   '-- Makefile
|-- frontend/
|   |-- src/                          # React source
|   |-- package.json
|   |-- package-lock.json
|   '-- Dockerfile
|-- .github/workflows/ci.yml          # Backend and frontend CI
|-- docker-compose.yml                # Complete local stack
|-- Makefile                          # Monorepo commands
'-- README.md
~~~

The backend uses a flat package layout inside app/. Run Python commands from app/, or use the root Makefile, which selects the correct working directory.

## Prerequisites

For Docker development:

- Docker Engine or Docker Desktop
- Docker Compose v2
- GNU Make

For local application development:

- Python 3.11 or newer
- Node.js 20 or newer
- npm
- GNU Make
- Docker Compose for the backing services

## Docker quick start

Create the local configuration:

~~~bash
cp app/.env.example app/.env
~~~

Review the development credentials, then start the stack:

~~~bash
make docker-up
~~~

The API container applies pending Alembic migrations before Uvicorn starts.

Check services and API health:

~~~bash
docker compose --env-file app/.env ps
curl http://localhost:8000/health
~~~

Useful URLs:

- Frontend: http://localhost:5173
- API documentation: http://localhost:8000/docs
- OpenAPI schema: http://localhost:8000/openapi.json
- MinIO console: http://localhost:9001
- Qdrant dashboard: http://localhost:6333/dashboard

Follow API and worker logs:

~~~bash
docker compose --env-file app/.env logs -f api worker
~~~

Stop services while keeping data:

~~~bash
make docker-down
~~~

To reset all local service data:

~~~bash
docker compose --env-file app/.env down --volumes
~~~

The last command permanently deletes the local PostgreSQL, Redis, MinIO, and Qdrant volumes.

## Local development

### 1. Configure the application

~~~bash
cp app/.env.example app/.env
~~~

The example file uses localhost, which is correct when the API and worker run on the host.

### 2. Install backend and frontend dependencies

~~~bash
make install
~~~

This creates app/.venv, installs backend development dependencies, and installs frontend packages.

Manual equivalent:

~~~bash
cd app
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
cd ../frontend
npm install
cd ..
~~~

Windows PowerShell activation:

~~~powershell
app\.venv\Scripts\Activate.ps1
~~~

### 3. Start infrastructure only

~~~bash
docker compose --env-file app/.env up -d postgres redis minio minio-init qdrant
~~~

### 4. Apply migrations

~~~bash
make migrate
~~~

### 5. Run the processes

Open separate terminals at the repository root:

~~~bash
make backend
~~~

~~~bash
make worker
~~~

~~~bash
make frontend
~~~

The API uses reload mode, the worker consumes the ingestion queue, and Vite serves the frontend on port 5173.

## Configuration

Settings come from process environment variables and app/.env. Process variables take precedence. Never commit app/.env.

| Variable | Purpose | Development value |
| --- | --- | --- |
| APP_ENV | development, test, staging, or production | development |
| APP_LOG_LEVEL | Log threshold | INFO |
| APP_CORS_ORIGINS | JSON array or CSV browser origins | Local frontend |
| DATABASE_URL | Async PostgreSQL URL | Local PostgreSQL |
| REDIS_URL | Task-status Redis database | redis://localhost:6379/0 |
| CELERY_BROKER_URL | Celery broker | redis://localhost:6379/1 |
| CELERY_RESULT_BACKEND | Celery results | redis://localhost:6379/2 |
| MINIO_ENDPOINT | Host and port without URL scheme | localhost:9000 |
| MINIO_ACCESS_KEY | MinIO access key | Development credential |
| MINIO_SECRET_KEY | MinIO secret key | Development credential |
| MINIO_BUCKET | Object bucket | scenesearch |
| QDRANT_HOST | Qdrant host | localhost |
| QDRANT_COLLECTION | Vector collection | scenes |
| OPENAI_API_KEY | Future agent API key | Empty |
| MODEL_NAME | Future agent model | gpt-4o-mini |

Compose overrides hostnames so containers communicate on the internal network. Do not reuse example credentials in a deployed environment.

## API guide

Application routes are under /api/v1, except /health.

### Health

~~~bash
curl http://localhost:8000/health
~~~

~~~json
{"status":"ok","environment":"development"}
~~~

### Submit ingestion

~~~bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"video_path":"/data/example.mp4"}'
~~~

The endpoint returns HTTP 202 and a task record. A local path must be accessible to the worker or mounted into its container. HTTP URLs pass validation, but remote media downloading belongs to the next phase.

### Read task status

~~~bash
curl http://localhost:8000/api/v1/tasks/<task-id>
~~~

States are pending, queued, processing, retrying, completed, and failed.

### Agent scaffold

~~~bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Find scenes containing a red car"}'
~~~

The current agent returns scaffold output; it does not perform semantic search yet. GET /api/v1/status reports graph availability.

## Database migrations

Apply pending migrations:

~~~bash
make migrate
~~~

Create a migration after changing database models:

~~~bash
make migration name=add_scene_metadata
~~~

Review generated column types, constraints, indexes, defaults, and downgrade behavior before committing.

Useful commands from app/:

~~~bash
.venv/bin/python -m alembic current
.venv/bin/python -m alembic history
.venv/bin/python -m alembic downgrade -1
~~~

Compose runs migrations on API startup for local convenience. Staging and production should run migrations as a separate release step.

## Dependencies and quality checks

Backend dependencies live in app/pyproject.toml and app/requirements.lock. After changing them:

~~~bash
make lock
make test
make lint
~~~

Commit both files together.

Frontend dependencies live in frontend/package.json and frontend/package-lock.json. After changing them:

~~~bash
npm --prefix frontend install
npm --prefix frontend run build
~~~

Other validation commands:

~~~bash
docker compose --env-file app/.env config --quiet
python -m compileall -q app
~~~

CI runs backend linting, formatting, tests, and the frontend build on pull requests and pushes to main.

Test directories:

- tests/unit/: isolated logic
- tests/test_api/: HTTP contracts
- tests/test_agents/: LangGraph behavior
- tests/integration/: backing-service integration
- tests/e2e/: complete user workflows

Use the integration and e2e pytest markers for infrastructure-dependent tests.

## Development conventions

- Keep HTTP contracts in schemas/.
- Keep route handlers small; move workflows into services, repositories, or pipelines.
- Access external systems through infrastructure/ adapters.
- Use Alembic for every database schema change.
- Use async libraries in API paths and move blocking SDK calls to a worker thread.
- Make Celery tasks idempotent because late acknowledgements may cause redelivery.
- Add type hints to public functions and keep Ruff checks passing.
- Use English for code, documentation, comments, logs, and API text.
- Comment non-obvious reasons or constraints, not line-by-line behavior.
- Write scoped TODOs, for example: TODO(search): Add metadata filters.
- Add unit tests for logic, integration tests for adapters, and E2E tests for critical workflows.
- Never commit secrets, generated media, local data, or model weights.

## Troubleshooting

### Backend environment is missing

~~~bash
make install
~~~

Backend commands expect app/.venv/bin/python.

### A port is already in use

Stop the conflicting process or change its port in app/.env. The stack uses 5173, 5432, 6379, 6333, 6334, 8000, 9000, and 9001.

### An infrastructure dependency is unavailable

~~~bash
docker compose --env-file app/.env ps
docker compose --env-file app/.env logs postgres redis minio qdrant
~~~

For host-based development, confirm that database, Redis, MinIO, and Qdrant settings use localhost rather than Compose service names.

### Tasks remain queued

~~~bash
docker compose --env-file app/.env logs worker
docker compose --env-file app/.env exec worker celery -A worker.celery_app inspect active_queues
~~~

Confirm that the worker consumes the ingestion queue.

## Next-phase plan

The next phase should deliver one complete ingestion-to-search slice before expanding the agent.

### Phase 1: Real ingestion pipeline

Goal: convert an accepted video into indexed scene records.

- Define video, scene, asset, and ingestion SQLAlchemy models.
- Add migrations and indexes.
- Implement safe local and HTTP source acquisition.
- Validate media type, size, duration, and decode limits.
- Store original videos and thumbnails in MinIO.
- Decode videos and sample frames in configurable batches.
- Load one embedding model per worker process.
- Generate normalized embeddings and upsert them into Qdrant.
- Store timestamps, object keys, dimensions, and model version.
- Make ingestion idempotent with a stable video checksum.
- Add real infrastructure integration tests.

Exit criteria:

- A test video completes the API-to-worker ingestion flow.
- Re-ingestion does not duplicate scenes.
- Every vector links to durable metadata and a thumbnail.
- Failures leave an actionable task state and no orphaned partial index.

### Phase 2: Semantic search API

Goal: return relevant timestamped scenes for natural-language queries.

- Add versioned search request and response schemas.
- Embed text with the model paired to the scene encoder.
- Implement Qdrant similarity search, pagination, and filters.
- Hydrate results with PostgreSQL metadata and MinIO URLs.
- Add score thresholds, deterministic ordering, and limits.
- Create a small labeled retrieval evaluation set.

Exit criteria:

- POST /api/v1/search returns ranked scenes.
- Search supports video, time-range, and score filters.
- Integration tests cover empty results and backend failures.

### Phase 3: Usable frontend

Goal: support the complete workflow in the browser.

- Add video submission and task progress.
- Add semantic search with loading, empty, and error states.
- Show thumbnails, timestamps, scores, and metadata.
- Seek the video player to a selected scene.
- Generate a typed API client from OpenAPI.
- Add component and browser-level E2E tests.

Exit criteria:

- A user can ingest, monitor, search, and open a scene.
- Success and failure paths are tested.

### Phase 4: Operational hardening

Goal: prepare the completed flow for controlled deployment.

- Add authentication, authorization, ownership, and rate limits.
- Restrict remote ingestion and defend against SSRF.
- Add metrics, tracing, readiness checks, and alerts.
- Split lightweight API and ML worker images.
- Configure CPU/GPU queues and resource limits.
- Reconcile Redis/PostgreSQL status divergence.
- Add backups, retention, and deletion workflows.
- Add load, recovery, and security tests.
- Document deployment, rollback, and model migrations.

The sequence is intentional: ingestion first, retrieval second, user experience third, and production hardening after the full workflow is measurable.