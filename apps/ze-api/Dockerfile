# Production image for Ze backend (Fly.io / docker-compose).
# Build context: repository root (see docker-compose.yml).
# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# libgomp: runtime dependency for PyTorch CPU wheels
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY core/ core/
COPY plugins/ plugins/
COPY apps/ze-api/ apps/ze-api/

RUN uv sync --no-dev --package ze-api

ENV HF_HOME=/app/.cache/huggingface
ENV TRANSFORMERS_CACHE=/app/.cache/huggingface
RUN mkdir -p "$HF_HOME" && python -c "\
from ze_core.embeddings import get_embedder; \
from ze_core.nli import get_nli_model; \
get_embedder(); \
get_nli_model(); \
print('models cached')"

ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app/apps/ze-api

EXPOSE 8000

CMD ["uvicorn", "ze_api.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
