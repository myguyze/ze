# ── Ze — project Makefile ─────────────────────────────────────────────────────

.DEFAULT_GOAL := help

ZE      := apps/ze-api
ZE_CORE := core/ze-core
ZE_WEB  := apps/ze-web

LOG_FILE     ?= $(ZE)/logs/ze.log
DB_SYNC_URL  ?= postgresql+psycopg2://ze:ze@localhost:5432/ze
ZE_MIGRATE   := cd $(ZE) && DATABASE_URL_SYNC=$(DB_SYNC_URL) uv run python -m ze_api.migrate

# ── Help ──────────────────────────────────────────────────────────────────────
.PHONY: help
help:
	@echo ""
	@echo "  Ze — available targets"
	@echo ""
	@echo "  Setup"
	@echo "    install              Install Python workspace dependencies (uv sync)"
	@echo "    web-install          Install React web app dependencies (bun install)"
	@echo "    google-auth          One-time Google OAuth2 flow (Calendar + Gmail)"
	@echo "    generate-ze-api-key  Generate or refresh ZE_API_KEY in .env"
	@echo ""
	@echo "  Database"
	@echo "    db-up            Start Postgres via docker-compose"
	@echo "    db-down          Stop Postgres"
	@echo "    db-reset         Drop + recreate ze database and apply all migrations"
	@echo "    reset-personal-state  Delete learned personal state after CONFIRM=RESET"
	@echo "    migrate          Apply all pending migrations (upgrade heads)"
	@echo "    migrate-down     Roll back one migration step"
	@echo "    migrate-status   Show current migration revision"
	@echo "    migrate-history  List all migrations"
	@echo "    migrate-stamp    Stamp existing DB to squashed heads (run once after squash)"
	@echo ""
	@echo "  Development"
	@echo "    dev              Start backend only (uvicorn --reload on :8000)"
	@echo "    web              Start React web app (bun dev on :5173)"
	@echo "    dev-full         Start backend + React web app (Ctrl-C stops both)"
	@echo "    dev-eval         Start backend without background jobs (use before evals)"
	@echo "    logs             Tail the server log file (LOG_FILE=$(LOG_FILE))"
	@echo ""
	@echo "  Web app"
	@echo "    web-install      Install React web app dependencies (bun install)"
	@echo "    web              Start React web dev server (:5173)"
	@echo "    web-build        Build React web app for production"
	@echo "    web-test         Run React web app tests (vitest)"
	@echo ""
	@echo "  Eval (requires 'make dev-eval' running)"
	@echo "    eval             Run full eval suite — routing accuracy only (cheap)"
	@echo "    eval-judge       Run eval suite with LLM quality judge (costs tokens)"
	@echo "    eval-report      Show last eval run summary"
	@echo "    eval-diff        Compare last two eval runs (regression detection)"
	@echo "    eval-server      Start MCP eval server (for Claude Code / Cursor / Codex)"
	@echo "    eval-clean       Delete eval-namespaced rows from DB"
	@echo ""
	@echo "  Testing"
	@echo "    test             Run ze-api tests (skips slow embedding tests)"
	@echo "    test-core        Run ze-core tests"
	@echo "    test-personal    Run ze-personal tests"
	@echo "    test-prospecting Run ze-prospecting tests"
	@echo "    test-email       Run ze-email tests"
	@echo "    test-calendar    Run ze-calendar tests"
	@echo "    test-news        Run ze-news tests"
	@echo "    test-all         Run all tests across all packages (includes slow)"
	@echo ""
	@echo "  Code quality"
	@echo "    lint             Lint all packages with ruff"
	@echo "    format           Auto-format and fix all packages with ruff"
	@echo "    clean            Remove __pycache__, .pytest_cache, .ruff_cache, *.pyc"
	@echo ""
	@echo "  Code generation"
	@echo "    generate-components  Regenerate server-driven UI component descriptors"
	@echo ""
	@echo "  Docker"
	@echo "    docker-up        Start all services via docker-compose"
	@echo "    docker-down      Stop all services"
	@echo "    docker-build     Build all Docker images"
	@echo ""

# ── Setup ─────────────────────────────────────────────────────────────────────
.PHONY: install web-install google-auth generate-ze-api-key

install:
	uv sync

web-install:
	cd $(ZE_WEB) && bun install

google-auth:
	uv run python $(ZE)/scripts/google_auth.py

generate-ze-api-key:
	uv run python $(ZE)/scripts/generate_ze_api_key.py $(if $(ZE_API_TOKEN),--token $(ZE_API_TOKEN))

# ── Database ──────────────────────────────────────────────────────────────────
.PHONY: db-up db-down db-reset reset-personal-state migrate migrate-down migrate-status migrate-history migrate-stamp

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
	$(ZE_MIGRATE) upgrade

reset-personal-state:
	@if [ "$(CONFIRM)" != "RESET" ]; then \
		echo "Refusing to reset. Re-run with CONFIRM=RESET"; \
		exit 1; \
	fi
	cd $(ZE) && uv run python scripts/reset_personal_state.py --scope personal_state --confirm RESET

migrate:
	$(ZE_MIGRATE) upgrade

migrate-down:
	$(ZE_MIGRATE) downgrade -1

migrate-status:
	$(ZE_MIGRATE) current

migrate-history:
	$(ZE_MIGRATE) history

# Update the head IDs here after each migration squash (see apps/ze-api/migrations/).
migrate-stamp:
	$(ZE_MIGRATE) stamp --purge zc004 ze001

# ── Development ───────────────────────────────────────────────────────────────
.PHONY: dev web dev-full dev-eval logs

dev:
	AUTO_MIGRATE=true LOG_DEV=true LOG_FILE=$(LOG_FILE) uv run uvicorn ze_api.api.app:app --reload --host 0.0.0.0 --port 8000

web:
	cd $(ZE_WEB) && bun run dev

# Starts the backend in the background, waits for :8000 to be ready, then starts
# the React web app. Ctrl-C stops both.
dev-full:
	@trap 'kill %1 2>/dev/null; exit 0' INT TERM; \
	AUTO_MIGRATE=true LOG_DEV=true LOG_FILE=$(LOG_FILE) uv run uvicorn ze_api.api.app:app --reload --host 0.0.0.0 --port 8000 & \
	until nc -z localhost 8000 2>/dev/null; do sleep 1; done; \
	echo "Backend ready — starting React web app..."; \
	cd $(ZE_WEB) && bun run dev; \
	kill %1 2>/dev/null

dev-eval:
	AUTO_MIGRATE=true PUBLIC_URL= LOG_DEV=true LOG_FILE=$(LOG_FILE) uv run uvicorn ze_api.api.app:app --reload --host 0.0.0.0 --port 8000

logs:
	tail -f $(LOG_FILE)

# ── Eval ──────────────────────────────────────────────────────────────────────
.PHONY: eval eval-judge eval-report eval-diff eval-server eval-clean

eval:
	uv run python eval/run.py

eval-judge:
	uv run python eval/run.py --judge

eval-report:
	uv run python eval/run.py report

eval-diff:
	uv run python eval/run.py report --compare

eval-server:
	uv run python eval/server.py

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
	@echo "Removing eval fixture rows (update these when eval fixtures change)..."
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
.PHONY: test test-core test-personal test-prospecting test-email test-calendar test-news test-all

test:
	uv run pytest $(ZE)/tests -m 'not slow' -q

test-core:
	uv run pytest $(ZE_CORE)/tests -q

test-personal:
	uv run pytest plugins/ze-personal/tests -q

test-prospecting:
	uv run pytest plugins/ze-prospecting/tests -q

test-email:
	uv run pytest plugins/ze-email/tests -q

test-calendar:
	uv run pytest plugins/ze-calendar/tests -q

test-news:
	uv run pytest plugins/ze-news/tests -q

test-all:
	uv run pytest $(ZE)/tests -q && \
	uv run pytest $(ZE_CORE)/tests -q && \
	uv run pytest plugins/ze-personal/tests -q && \
	uv run pytest plugins/ze-prospecting/tests -q && \
	uv run pytest plugins/ze-email/tests -q && \
	uv run pytest plugins/ze-calendar/tests -q && \
	uv run pytest plugins/ze-news/tests -q

# ── Web app ───────────────────────────────────────────────────────────────────
.PHONY: web-build web-test

web-build:
	cd $(ZE_WEB) && bun run build

web-test:
	cd $(ZE_WEB) && bun run test

# ── Code generation ───────────────────────────────────────────────────────────
.PHONY: generate-components

generate-components:
	uv run scripts/generate_components.py

# ── Code quality ──────────────────────────────────────────────────────────────
.PHONY: lint format clean

lint:
	uv run ruff check .

format:
	uv run ruff format .
	uv run ruff check --fix .

clean:
	find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '.pytest_cache' -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '.ruff_cache' -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete 2>/dev/null || true

# ── Docker ────────────────────────────────────────────────────────────────────
.PHONY: docker-up docker-down docker-build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-build:
	docker compose build
