.PHONY: install lock migrate migration dev backend worker frontend test lint docker-up docker-down

COMPOSE := docker compose --env-file app/.env

install:
	$(MAKE) -C app install
	npm --prefix frontend install

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

lint:
	$(MAKE) -C app lint

docker-up:
	$(COMPOSE) up -d --build --wait

docker-down:
	$(COMPOSE) down
