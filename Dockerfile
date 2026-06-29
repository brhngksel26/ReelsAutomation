# syntax=docker/dockerfile:1

# Stage 1: Builder — resolve and install dependencies into an isolated virtualenv
FROM python:3.10-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Install dependencies first (layer cache friendly)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Copy application code and finalize the environment
COPY alembic.ini ./
COPY alembic ./alembic
COPY scripts ./scripts
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Stage 2: Runtime — slim image with only the venv and application code
FROM python:3.10-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/src \
    PATH="/app/.venv/bin:$PATH"

RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid appgroup --create-home --home-dir /app --shell /usr/sbin/nologin appuser

WORKDIR /src

COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appgroup /app/alembic.ini ./
COPY --from=builder --chown=appuser:appgroup /app/alembic ./alembic
COPY --from=builder --chown=appuser:appgroup /app/scripts ./scripts
COPY --from=builder --chown=appuser:appgroup /app/src ./src

RUN mkdir -p /storage/videos /storage/audio \
    && chown -R appuser:appgroup /storage

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/openapi.json')" || exit 1

CMD ["sh", "scripts/start.sh"]
