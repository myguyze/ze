# Production image for Ze backend (Fly.io / docker-compose).
# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# libgomp: runtime dependency for PyTorch CPU wheels
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY ze ./ze
COPY config ./config
COPY migrations ./migrations
COPY alembic.ini ./

RUN uv sync --no-dev

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

CMD ["uvicorn", "ze.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
