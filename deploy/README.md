# Production deployment

`docker-compose.deploy.yml` is the single production stack. It runs the UI,
API, worker, PostgreSQL, Redis, and the on-demand Qwen embedding GPU service.
Qdrant and MinIO are remote and come from `app/.env`.

On the shared server, Qdrant is already published on host port `6335`. The
deploy stack defaults to `http://host.docker.internal:6335`; override it with
`DEPLOY_QDRANT_URL` when Qdrant lives elsewhere.

## Manual deployment

```bash
docker compose --env-file app/.env -f docker-compose.deploy.yml \
  up -d --build --remove-orphans
```

The UI is published on `DEPLOY_PORT` (default `8088`). Load the Qwen model from
the ingestion page before search or ingestion.

## GitHub Actions production environment

Create a protected GitHub Environment named `production`, then add these
secrets:

| Secret | Value |
|---|---|
| `DEPLOY_HOST` | Server hostname or IP |
| `DEPLOY_SSH_PORT` | SSH port, currently `10036` on the shared server |
| `DEPLOY_USER` | SSH user allowed to run Docker |
| `DEPLOY_PATH` | Absolute checkout path, for example `/home/sysadmin/P-081` |
| `DEPLOY_SSH_KEY` | Private SSH deployment key |
| `DEPLOY_KNOWN_HOSTS` | Pinned server host-key line from `ssh-keyscan` after independently verifying its fingerprint |
| `PRODUCTION_ENV_B64` | Base64 of the complete production `app/.env` |

Generate and verify the pinned host key using the configured SSH port:

```bash
ssh-keyscan -p 10036 103.130.211.150
```

Compare its fingerprint with the server administrator before saving the full
line as `DEPLOY_KNOWN_HOSTS`.

Generate the environment secret without committing `.env`:

```bash
base64 -w 0 app/.env
```

On macOS use:

```bash
base64 < app/.env | tr -d '\n'
```

Pushes to `main` deploy only after backend, frontend, and Compose validation
pass. The workflow deploys the exact tested commit, refuses a dirty server
worktree, writes `app/.env` with mode `600`, and smoke-tests `/health`.

Never put Qdrant, NVIDIA, MinIO, database, or JWT credentials in Git.
