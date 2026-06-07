# ── Ze — project Makefile ─────────────────────────────────────────────────────

.DEFAULT_GOAL := help

ZE      := packages/ze-api
ZE_CORE := packages/ze-core

DB_SYNC_URL  ?= postgresql+psycopg2://ze:ze@localhost:5432/ze
ZE_MIGRATE   := cd $(ZE) && DATABASE_URL_SYNC=$(DB_SYNC_URL) uv run python -m ze_api.migrate

# ── Help ──────────────────────────────────────────────────────────────────────
.PHONY: help
help:
	@echo ""
	@echo "  Ze — available targets"
	@echo ""
	@echo "  Setup"
	@echo "    install              Install all workspace dependencies"
	@echo "    google-auth          One-time Google OAuth2 flow (Calendar + Gmail)"
	@echo "    generate-ze-api-key  Generate or refresh ZE_API_KEY in .env"
	@echo ""
	@echo "  Database"
	@echo "    db-up          Start Postgres via docker-compose"
	@echo "    db-down        Stop Postgres"
	@echo "    db-reset       Drop + recreate the ze database"
	@echo "    migrate        Apply all pending migrations (upgrade heads)"
	@echo "    migrate-down   Roll back one migration step"
	@echo "    migrate-status Show current migration revision"
	@echo "    migrate-history List all migrations"
	@echo "    migrate-stamp   Stamp existing DB to squashed heads (run once after squash)"
	@echo ""
	@echo "  Development"
	@echo "    dev            Start dev server (uvicorn --reload, REST API only)"
	@echo "    dev-poll       Start Telegram long-polling (interact via Telegram locally)"
	@echo "    dev-eval       Start REST API without Telegram webhook (for running evals)"
	@echo ""
	@echo "  Eval (requires 'make dev-eval' running)"
	@echo "    eval           Run full eval suite — routing accuracy only (cheap)"
	@echo "    eval-judge     Run eval suite with LLM quality judge (costs tokens)"
	@echo "    eval-report    Show last eval run summary"
	@echo "    eval-diff      Compare last two eval runs (regression detection)"
	@echo "    eval-server    Start MCP eval server (for Claude Code / Cursor / Codex)"
	@echo "    eval-clean     Delete eval-namespaced rows from DB"
	@echo ""
	@echo "  Testing"
	@echo "    test           Run ze tests (excludes slow embedding tests)"
	@echo "    test-core      Run ze-core tests"
	@echo "    test-all       Run all tests including slow ones"
	@echo ""
	@echo "  Code quality"
	@echo "    lint           Lint all packages with ruff"
	@echo ""
	@echo "  Docker"
	@echo "    docker-up      Start all services via docker-compose"
	@echo "    docker-down    Stop all services"
	@echo "    docker-build   Build all Docker images"
	@echo ""

# ── Setup ─────────────────────────────────────────────────────────────────────
.PHONY: install google-auth generate-ze-api-key

install:
	uv sync

google-auth:
	uv run python $(ZE)/scripts/google_auth.py

generate-ze-api-key:
	uv run python $(ZE)/scripts/generate_ze_api_key.py $(if $(ZE_API_TOKEN),--token $(ZE_API_TOKEN))

# ── Database ──────────────────────────────────────────────────────────────────
.PHONY: db-up db-down db-reset migrate migrate-down migrate-status migrate-history migrate-stamp

db-up:
	docker compose up -d postgres
	@echo "Waiting for Postgres to be ready..."
	@until docker compose exec -T postgres pg_isready -U ze -q; do sleep 1; done
	@echo "Postgres is ready."

db-down:
	docker compose stop postgres

db-reset:
	docker compose exec -T postgres psql -U ze -c "DROP DATABASE IF EXISTS ze"
	docker compose exec -T postgres psql -U ze -c "CREATE DATABASE ze"

migrate:
	$(ZE_MIGRATE) upgrade

migrate-down:
	$(ZE_MIGRATE) downgrade

migrate-status:
	$(ZE_MIGRATE) current

migrate-history:
	$(ZE_MIGRATE) history

migrate-stamp:
	$(ZE_MIGRATE) stamp --purge zc004 ze001

# ── Development ───────────────────────────────────────────────────────────────
.PHONY: dev dev-poll dev-eval

dev:
	LOG_FILE=$(ZE)/logs/ze.log uv run uvicorn ze_api.api.app:app --reload --host 0.0.0.0 --port 8000

dev-poll:
	LOG_FILE=$(ZE)/logs/ze.log uv run python -m ze_api.dev_poll

dev-eval:
	PUBLIC_URL= LOG_FILE=$(ZE)/logs/ze.log uv run uvicorn ze_api.api.app:app --reload --host 0.0.0.0 --port 8000

# ── Eval ──────────────────────────────────────────────────────────────────────
.PHONY: eval eval-judge eval-report eval-diff eval-server eval-clean

eval:
	uv run python -m evals.runner

eval-judge:
	uv run python -m evals.runner --judge

eval-report:
	uv run python -m evals.report

eval-diff:
	uv run python -m evals.report --compare

eval-server:
	uv run python evals/mcp_server.py

eval-clean:
	@echo "Removing eval-namespaced rows from routing_log, checkpoints, llm_cost_log..."
	docker compose exec -T postgres psql -U ze -d ze -c \
		"DELETE FROM routing_log WHERE session_id LIKE 'eval-%';"
	docker compose exec -T postgres psql -U ze -d ze -c \
		"DELETE FROM llm_cost_log WHERE session_id LIKE 'eval-%';"
	docker compose exec -T postgres psql -U ze -d ze -c \
		"DELETE FROM checkpoint_blobs WHERE thread_id LIKE 'eval-%';"
	docker compose exec -T postgres psql -U ze -d ze -c \
		"DELETE FROM checkpoint_writes WHERE thread_id LIKE 'eval-%';"
	docker compose exec -T postgres psql -U ze -d ze -c \
		"DELETE FROM checkpoints WHERE thread_id LIKE 'eval-%';"
	@echo "Removing eval-created rows from outcome-verified tables..."
	docker compose exec -T postgres psql -U ze -d ze -c \
		"DELETE FROM user_reminders WHERE label ILIKE '%dentist%' OR label ILIKE '%build pipeline%' OR label ILIKE '%vitamins%';"
	docker compose exec -T postgres psql -U ze -d ze -c \
		"DELETE FROM workflows WHERE description ILIKE '%email%digest%' OR description ILIKE '%calendar%briefing%';"
	docker compose exec -T postgres psql -U ze -d ze -c \
		"DELETE FROM goals WHERE objective ILIKE '%books%' OR objective ILIKE '%rust%' OR objective ILIKE '%cli%';"
	docker compose exec -T postgres psql -U ze -d ze -c \
		"DELETE FROM user_facts WHERE value ILIKE '%dark mode%' OR value ILIKE '%rust%';"
	docker compose exec -T postgres psql -U ze -d ze -c \
		"DELETE FROM contacts WHERE name ILIKE '%pedro%' OR name ILIKE '%maria%';"

# ── Testing ───────────────────────────────────────────────────────────────────
.PHONY: test test-core test-all

test:
	uv run pytest $(ZE)/tests --ignore=$(ZE)/tests/test_embeddings.py -q

test-core:
	uv run pytest $(ZE_CORE)/tests -q

test-calendar:
	uv run pytest packages/ze-calendar/tests -q

test-all:
	uv run pytest $(ZE)/tests $(ZE_CORE)/tests -q && uv run pytest packages/ze-calendar/tests -q

# ── Code generation ───────────────────────────────────────────────────────────
.PHONY: generate-components

generate-components:
	uv run scripts/generate_components.py

# ── Code quality ──────────────────────────────────────────────────────────────
.PHONY: lint

lint:
	uv run ruff check $(ZE)/ze_api $(ZE)/tests $(ZE_CORE)/ze_core $(ZE_CORE)/tests packages/ze-calendar/ze_calendar packages/ze-google/ze_google

# ── Docker ────────────────────────────────────────────────────────────────────
.PHONY: docker-up docker-down docker-build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-build:
	docker compose build
