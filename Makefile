.PHONY: install install-ml lock migrate migration dev backend worker frontend test lint quality \
	frontend-test frontend-lint frontend-build \
	docker-up docker-infra docker-down docker-deploy \
	deploy deploy-gcp deploy-full deploy-api deploy-frontend deploy-local deploy-only \
	eval eval-dry eval-check

COMPOSE := docker compose --env-file app/.env -f docker-compose.yml
PYTHON ?= app/.venv/bin/python

.PHONY: local-build local-up local-down local-logs local-ps local-admin
local-build:
	$(COMPOSE) build

local-up:
	$(COMPOSE) up -d --build

local-down:
	$(COMPOSE) down

local-logs:
	$(COMPOSE) logs -f --tail=100

local-ps:
	$(COMPOSE) ps

local-admin:
	$(COMPOSE) exec api python -m services.bootstrap_admin

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

# All deployment aliases use the same source-build stack.
docker-deploy deploy deploy-gcp deploy-full deploy-api deploy-frontend deploy-local deploy-only:
	$(COMPOSE) up -d --build

config-check:
	$(COMPOSE) config --quiet
	PYTHONPATH=app $(PYTHON) -c 'from core.config import get_settings; get_settings(); print("Settings OK")'

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
