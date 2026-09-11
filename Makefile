.PHONY: install install-ml lock migrate migration dev backend worker frontend test lint quality \
	frontend-test frontend-lint frontend-build \
	docker-up docker-infra docker-down docker-deploy \
	deploy deploy-gcp deploy-full deploy-api deploy-frontend deploy-local deploy-only \
	eval eval-dry eval-check

COMPOSE := docker compose --env-file app/.env -f docker-compose.yml
PYTHON := app/.venv/bin/python

install:
	$(MAKE) -C app install
	npm --prefix frontend ci || npm --prefix frontend install

# The ML extra is installed separately: it pulls torch. The API needs it for
# query encoding on the host (`make backend`); the Docker API image stays slim.
install-ml:
	$(MAKE) -C app install-ml

lock:
	$(MAKE) -C app lock

migrate:
	$(MAKE) -C app migrate

migration:
	$(MAKE) -C app migration name="$(name)"

dev:
	$(COMPOSE) up --build

backend:
	$(MAKE) -C app dev

worker:
	$(MAKE) -C app worker

frontend:
	npm --prefix frontend run dev

test:
	$(MAKE) -C app test
	npm --prefix frontend test

lint:
	$(MAKE) -C app lint
	npm --prefix frontend run lint

frontend-test:
	npm --prefix frontend test

frontend-lint:
	npm --prefix frontend run lint

frontend-build:
	npm --prefix frontend run build

quality: lint test frontend-build

docker-up:
	$(COMPOSE) up -d --build

docker-down:
	$(COMPOSE) down

docker-logs:
	$(COMPOSE) logs -f

docker-ps:
	$(COMPOSE) ps

docker-worker:
	$(COMPOSE) up -d --build worker

docker-api:
	$(COMPOSE) up -d --build api

docker-embedding:
	$(COMPOSE) up -d --build embedding-api

docker-frontend:
	$(COMPOSE) up -d --build frontend

# 1-Compose Deployment on Server / VM (e.g. Google Cloud Compute Engine VM / Local)
deploy-compose:
	$(COMPOSE) up -d --build

deploy-vm:
	$(COMPOSE) up -d --build

# Shared-host stack: production UI + API on port 8088.
docker-deploy:
	DEPLOY_PORT="$(or $(DEPLOY_PORT),8088)" \
	DEPLOY_PUBLIC_ORIGIN="$(or $(DEPLOY_PUBLIC_ORIGIN),http://103.130.211.150:8088)" \
	bash scripts/deploy-shared.sh

# Google Cloud Run 1-Service Multi-Container Deployment (1 URL duy nhất: Frontend + API + AI + Worker)
deploy:
	bash scripts/deploy-multicontainer.sh

deploy-gcp:
	bash scripts/deploy-multicontainer.sh

deploy-cloudrun:
	bash scripts/deploy-multicontainer.sh

deploy-multicontainer:
	bash scripts/deploy-multicontainer.sh

deploy-run-compose:
	bash scripts/deploy-multicontainer.sh

deploy-only:
	bash scripts/deploy-multicontainer.sh --no-build

deploy-full:
	bash scripts/deploy-gcp.sh --full

deploy-all:
	bash scripts/deploy-gcp.sh --full

# Deploy full stack with Cloud Run GPU (NVIDIA Tesla T4)
deploy-gpu:
	bash scripts/deploy-gcp.sh --full --gpu nvidia-tesla-t4

deploy-api:
	bash scripts/deploy-gcp.sh --api-only

deploy-frontend:
	bash scripts/deploy-gcp.sh --frontend-only

deploy-local:
	bash scripts/deploy-gcp.sh --local

deploy-only:
	bash scripts/deploy-gcp.sh --deploy-only

# Retrieval evaluation. See app/eval/README.md for what each band can and cannot
# be scored against.
eval-dry:
	$(MAKE) -C app eval-dry

eval:
	$(MAKE) -C app eval mot=$(mot) out=$(out) EVAL_ARGS="$(EVAL_ARGS)"

eval-check:
	$(MAKE) -C app eval-check mot=$(mot)

eval-qwen:
	$(MAKE) -C app eval-qwen args="$(args)"
