# Reels Automation

Short-form video automation backend for Instagram Reels, YouTube Shorts, and TikTok.

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)
- Docker & Docker Compose (optional)

## Quick Start (Local)

```bash
cp .env.example .env
docker compose up -d reels_automation_database reels_automation_redis
uv sync
uv run alembic upgrade head
uv run uvicorn src.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

## Quick Start (Docker)

```bash
cp .env.example .env
docker compose up --build
```

## Celery (Worker + Beat)

```bash
# Terminal 1 — worker
uv run celery -A src.core.celery_app worker --loglevel=info

# Terminal 2 — beat scheduler
uv run celery -A src.core.celery_app beat --loglevel=info
```

Or via Docker Compose (includes `reels_automation_celery_worker` and `reels_automation_celery_beat`).

## Smoke Test

```bash
uv run python scripts/smoke_test.py
# BASE_URL=http://localhost:8000 uv run python scripts/smoke_test.py
```

## Tests

```bash
uv sync --group dev
uv run pytest
```

## API Endpoints (v1)

| Method | Path | Auth |
|--------|------|------|
| POST | `/api/v1/auth/register` | Public |
| POST | `/api/v1/auth/token` | Public |
| GET | `/api/v1/users/me` | Bearer |
| POST/GET/PUT/DELETE | `/api/v1/channels/` | Bearer + permission |
| POST | `/api/v1/platforms/connect` | Bearer + permission |
| GET | `/api/v1/platforms/status` | Bearer + permission |
| POST | `/api/v1/videos/schedule` | Bearer + permission |
| GET | `/api/v1/videos/upcoming` | Bearer + permission |
| GET | `/api/v1/videos/{id}/status` | Bearer + permission |
