# syntax=docker/dockerfile:1.7
FROM python:3.11-slim

WORKDIR /app

# Which optional dependency groups to install.
#
# The API currently needs only the core dependencies. The ingestion worker
# overrides this with "ml" because it decodes and embeds frames. Keep developer
# tooling out of runtime images; tests run in the host/CI development environment.
#
# Note for macOS: Docker Desktop cannot pass the Metal (MPS) device into a
# container, so a containerized worker falls back to CPU and runs roughly ten
# times slower. On a Mac, run the backing services with `make docker-infra` and
# the worker natively with `make worker` (ADR-0001).
ARG EXTRAS=""

# Triton may compile CUDA kernels at runtime. Keep the compiler toolchain in
# the ML image so inference cannot fail later with a missing gcc executable.
RUN case ",${EXTRAS}," in \
        *,ml,*) apt-get update \
            && apt-get install -y --no-install-recommends build-essential \
            && rm -rf /var/lib/apt/lists/* ;; \
    esac

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/home/appuser/.cache/huggingface \
    HUGGINGFACE_HUB_CACHE=/home/appuser/.cache/huggingface/hub

COPY pyproject.toml /app/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip \
    && if [ -n "${EXTRAS}" ]; then \
        pip install -e ".[${EXTRAS}]"; \
    else \
        pip install -e .; \
    fi

COPY . /app
RUN pip install --no-deps . \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /home/appuser/.cache/huggingface \
    && chown -R appuser:appuser /home/appuser/.cache \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
