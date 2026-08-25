.PHONY: install install-ml lock migrate migration dev backend worker frontend test lint quality \
	frontend-test frontend-lint frontend-build \
	docker-up docker-infra docker-down docker-deploy \
	eval eval-dry eval-check

COMPOSE := docker compose --env-file app/.env
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
	$(COMPOSE) up -d --wait postgres redis minio qdrant
	$(COMPOSE) run --rm minio-init
	$(COMPOSE) up -d --build --wait api worker frontend

# Preferred target on macOS. Docker Desktop cannot pass MPS through to a
# container, so the API and worker run natively via 'make backend' / 'make
# worker' while only the backing services stay containerized (ADR-0001).
docker-infra:
	$(COMPOSE) up -d --wait postgres redis minio qdrant
	$(COMPOSE) run --rm minio-init

docker-down:
	$(COMPOSE) down

# Shared-host stack: production UI + API with SigLIP on one port (default 8088).
# Does not bind 80/443 — those are Huy's mvp.viettech.fit. See deploy/README.md.
docker-deploy:
	DEPLOY_PORT="$(or $(DEPLOY_PORT),8088)" \
	DEPLOY_PUBLIC_ORIGIN="$(or $(DEPLOY_PUBLIC_ORIGIN),http://103.130.211.150:8088)" \
	bash scripts/deploy-shared.sh

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
