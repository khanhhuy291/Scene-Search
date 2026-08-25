.PHONY: install install-ml lock lock-ml migrate migration dev worker test lint \
	eval eval-dry eval-check

BOOTSTRAP_PYTHON ?= python3
PYTHON ?= .venv/bin/python
PYTHON_SOURCES := api core db eval infrastructure ml pipelines repositories schemas search services worker tests
TEST_ENV := OPENBLAS_NUM_THREADS=1
UV := $(shell which uv 2>/dev/null || (test -x $(HOME)/.local/bin/uv && echo $(HOME)/.local/bin/uv))

install:
	@test -x $(PYTHON) || ($(if $(UV),$(UV) venv --python 3.12 .venv,$(BOOTSTRAP_PYTHON) -m venv .venv))
	@if [ -n "$(UV)" ]; then \
		$(UV) pip install --python $(PYTHON) -r requirements.lock -e .; \
	else \
		$(PYTHON) -m pip install -r requirements.lock -e .; \
	fi

install-ml:
	@test -x $(PYTHON) || ($(if $(UV),$(UV) venv --python 3.12 .venv,$(BOOTSTRAP_PYTHON) -m venv .venv))
	@if [ -n "$(UV)" ]; then \
		$(UV) pip install --python $(PYTHON) -e ".[dev,ml]"; \
	else \
		$(PYTHON) -m pip install -e ".[dev,ml]"; \
	fi

lock: install
	@if [ -n "$(UV)" ]; then \
		$(UV) pip compile --extra dev --extra media --output-file requirements.lock pyproject.toml; \
	else \
		$(PYTHON) -m piptools compile --extra dev --extra media --output-file requirements.lock pyproject.toml; \
	fi

lock-ml: install
	@if [ -n "$(UV)" ]; then \
		$(UV) pip compile --extra dev --extra media --extra ml --output-file requirements.lock pyproject.toml; \
	else \
		$(PYTHON) -m piptools compile --extra dev --extra media --extra ml --output-file requirements.lock pyproject.toml; \
	fi

migrate:
	$(PYTHON) -m alembic upgrade head

migration:
	@test -n "$(name)" || (echo "Usage: make migration name=describe_change" && exit 2)
	$(PYTHON) -m alembic revision --autogenerate -m "$(name)"

dev:
	$(PYTHON) -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

worker:
	$(PYTHON) -m celery -A worker.celery_app:celery_app worker -Q ingestion --loglevel=INFO

test:
	@test -x $(PYTHON) || (echo "Backend environment is missing; run 'make install' first." && exit 2)
	$(TEST_ENV) $(PYTHON) -m pytest

lint:
	@test -x $(PYTHON) || (echo "Backend environment is missing; run 'make install' first." && exit 2)
	$(PYTHON) -m ruff check $(PYTHON_SOURCES)
	$(PYTHON) -m ruff format --check $(PYTHON_SOURCES)

# -- retrieval evaluation ------------------------------------------------------
#
# `eval-dry` needs nothing: it prints the suite and which bands are scorable.
# `eval` needs a reachable index and the label CSV that supplies ground truth.
# `eval-check` is what CI runs once a baseline has been recorded.
#
#   make eval mot=../data/mot_labels.csv out=../reports/eval

eval-dry:
	$(PYTHON) -m eval.cli --dry-run

eval:
	@test -n "$(mot)" || (echo "Usage: make eval mot=path/to/mot_labels.csv [out=../reports/eval]" && exit 2)
	$(TEST_ENV) $(PYTHON) -m eval.cli --mot-csv "$(mot)" $(if $(out),--out "$(out)",) $(EVAL_ARGS)

eval-check:
	@test -n "$(mot)" || (echo "Usage: make eval-check mot=path/to/mot_labels.csv" && exit 2)
	$(TEST_ENV) $(PYTHON) -m eval.cli --mot-csv "$(mot)" \
		--check-baseline eval/baselines/live.json

eval-qwen:
	$(PYTHON) eval/evaluate_qwen.py $(args)
