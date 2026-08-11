.PHONY: install lock migrate migration dev worker test lint

BOOTSTRAP_PYTHON ?= python3
PYTHON ?= $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; elif [ -x ../.venv/bin/python ]; then echo ../.venv/bin/python; else echo python3; fi)
PYTHON_SOURCES := agents api core db infrastructure ml models repositories schemas search services worker main.py config.py tests

install:
	@test -x .venv/bin/python || $(BOOTSTRAP_PYTHON) -m venv .venv
	$(PYTHON) -m pip install -e ".[dev]"

lock: install
	$(PYTHON) -m piptools compile --extra dev --output-file requirements.lock pyproject.toml

lock-ml: install
	$(PYTHON) -m piptools compile --extra dev --extra ml --output-file requirements.lock pyproject.toml

migrate:
	$(PYTHON) -m alembic upgrade head

migration:
	@test -n "$(name)" || (echo "Usage: make migration name=describe_change" && exit 2)
	$(PYTHON) -m alembic revision --autogenerate -m "$(name)"

dev:
	$(PYTHON) -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

worker:
	$(PYTHON) -m celery -A worker.celery_app:celery_app worker -Q ingestion --loglevel=INFO

test:
	@test -x $(PYTHON) || (echo "Backend environment is missing; run 'make install' first." && exit 2)
	$(PYTHON) -m pytest

lint:
	@test -x $(PYTHON) || (echo "Backend environment is missing; run 'make install' first." && exit 2)
	$(PYTHON) -m ruff check $(PYTHON_SOURCES)
	$(PYTHON) -m ruff format --check $(PYTHON_SOURCES)
