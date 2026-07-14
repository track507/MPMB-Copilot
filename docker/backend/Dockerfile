# Multi-stage build for smallest final image
ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files
COPY backend/pyproject.toml backend/uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev --no-cache

# Final stage - minimal runtime
FROM python:${PYTHON_VERSION}-slim-bookworm

# Install PostgreSQL client libraries
# curl is needed for healthcheck (mainly for Qdrant)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Set environment
# DATA_DIR/FASTEMBED_CACHE_DIR must be absolute here: the code anchors relative data
# paths to the repo root, which resolves to / inside the container (code lives at /app/app)
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    TRANSFORMERS_OFFLINE=0 \
    HF_HOME=/tmp/huggingface \
    DATA_DIR=/app/data \
    FASTEMBED_CACHE_DIR=/app/data/models/fastembed

WORKDIR /app

# Create logs directory
RUN mkdir -p /app/logs /app/data/chunked_output /app/data/index_cache /app/data/uploads

# Copy application code (from backend/ subdirectory)
COPY backend/app /app/app

# Seed small runtime data files that the app expects to exist.
COPY data/intent_examples.json /app/data/intent_examples.json
COPY data/settings.json /app/data/settings.json

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["/app/.venv/bin/python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
