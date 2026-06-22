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
	@echo "    web-test         Run React web app tests (vitest) — alias for test-web"
	@echo ""
	@echo "  Eval (requires 'make dev-eval' running)"
	@echo "    eval             Run full eval suite — routing accuracy only (cheap)"
	@echo "    eval-judge       Run eval suite with LLM quality judge (costs tokens)"
	@echo "    eval-report      Show last eval run summary"
	@echo "    eval-diff        Compare last two eval runs (regression detection)"
	@echo "    eval-server      Start MCP eval server (for Claude Code / Cursor / Codex)"
	@echo "    eval-clean       Delete eval-namespaced rows from DB"
	@echo ""
	@echo "  Testing (see docs/testing.md)"
	@echo "    test / test-api      Run ze-api tests (skips slow)"
	@echo "    test-core            Run ze-core tests"
	@echo "    test-agents          Run ze-agents tests"
	@echo "    test-plugin          Run ze-plugin tests"
	@echo "    test-sdk             Run ze-sdk tests"
	@echo "    test-proactive       Run ze-proactive tests"
	@echo "    test-memory          Run ze-memory tests"
	@echo "    test-onboarding      Run ze-onboarding tests"
	@echo "    test-correlation     Run ze-correlation tests"
	@echo "    test-browser         Run ze-browser tests"
	@echo "    test-notifications   Run ze-notifications tests"
	@echo "    test-components      Run ze-components tests"
	@echo "    test-eval            Run ze-eval tests"
	@echo "    test-google          Run ze-google tests"
	@echo "    test-ingestion       Run ze-ingestion tests"
	@echo "    test-automation      Run ze-automation tests"
	@echo "    test-trading212      Run ze-trading212 tests"
	@echo "    test-personal        Run ze-personal tests"
	@echo "    test-email           Run ze-email tests"
	@echo "    test-calendar        Run ze-calendar tests"
	@echo "    test-prospecting     Run ze-prospecting tests"
	@echo "    test-news            Run ze-news tests"
	@echo "    test-web / web-test  Run ze-web tests (vitest)"
	@echo "    test-all             Run all package tests (includes slow)"
	@echo ""
	@echo "  Code quality"
	@echo "    lint             Lint all packages with ruff"
	@echo "    format           Auto-format and fix all packages with ruff"
	@echo "    clean            Remove __pycache__, .pytest_cache, .ruff_cache, *.pyc"
	@echo ""
	@echo "  Code generation"
	@echo "    codegen              Regenerate @ze/client and @ze/ui artifacts"
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
	uv run python scripts/google_auth.py

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
	uv run python scripts/reset_personal_state.py --scope personal_state --confirm RESET

migrate:
	$(ZE_MIGRATE) upgrade

migrate-down:
	$(ZE_MIGRATE) downgrade -1

migrate-status:
	$(ZE_MIGRATE) current

migrate-history:
	$(ZE_MIGRATE) history

# Stamp existing DB at all current heads after migration restructure.
# Run once on existing DBs that were on the old ze001–ze014 layout.
migrate-stamp:
	$(ZE_MIGRATE) stamp --purge zc018 zn002 zm008 zo001 zcor001 zcal001 zpros001 zpro001 zi001 zfin002

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
# Convention: make test-<short-name> from repo root. See docs/testing.md.
PYTEST      := uv run pytest
PYTEST_SLOW := $(PYTEST) -q
PYTEST_FAST := $(PYTEST) -m 'not slow' -q
pytest_pkg  = $(if $(SLOW),$(PYTEST_SLOW),$(PYTEST_FAST)) $(1)

# Ordered list for test-all (core → integrations → plugins → apps)
TEST_PY_PACKAGES := \
	test-agents \
	test-plugin \
	test-sdk \
	test-proactive \
	test-memory \
	test-onboarding \
	test-correlation \
	test-browser \
	test-notifications \
	test-components \
	test-eval \
	test-google \
	test-trading212 \
	test-ingestion \
	test-automation \
	test-core \
	test-personal \
	test-email \
	test-calendar \
	test-prospecting \
	test-news \
	test-api

.PHONY: test test-api test-core test-agents test-plugin test-sdk test-proactive \
	test-memory test-onboarding test-correlation test-browser test-notifications \
	test-components test-eval test-google test-trading212 test-ingestion test-automation test-personal test-prospecting test-email \
	test-calendar test-news test-all test-web web-test

test test-api:
	$(call pytest_pkg,apps/ze-api/tests)

test-core:
	$(call pytest_pkg,core/ze-core/tests)

test-agents:
	$(call pytest_pkg,core/ze-agents/tests)

test-plugin:
	$(call pytest_pkg,core/ze-plugin/tests)

test-sdk:
	$(call pytest_pkg,core/ze-sdk/tests)

test-proactive:
	$(call pytest_pkg,core/ze-proactive/tests)

test-memory:
	$(call pytest_pkg,core/ze-memory/tests)

test-ingestion:
	$(call pytest_pkg,core/ze-ingestion/tests)

test-automation:
	$(call pytest_pkg,core/ze-automation/tests)

test-onboarding:
	$(call pytest_pkg,core/ze-onboarding/tests)

test-correlation:
	$(call pytest_pkg,core/ze-correlation/tests)

test-browser:
	$(call pytest_pkg,core/ze-browser/tests)

test-notifications:
	$(call pytest_pkg,core/ze-notifications/tests)

test-components:
	$(call pytest_pkg,core/ze-components/tests)

test-eval:
	$(call pytest_pkg,core/ze-eval/tests)

test-google:
	$(call pytest_pkg,integrations/ze-google/tests)

test-trading212:
	$(call pytest_pkg,integrations/ze-trading212/tests)

test-personal:
	$(call pytest_pkg,plugins/ze-personal/tests)

test-prospecting:
	$(call pytest_pkg,plugins/ze-prospecting/tests)

test-email:
	$(call pytest_pkg,plugins/ze-email/tests)

test-calendar:
	$(call pytest_pkg,plugins/ze-calendar/tests)

test-news:
	$(call pytest_pkg,plugins/ze-news/tests)

test-all:
	@set -e; for t in $(TEST_PY_PACKAGES); do $(MAKE) SLOW=1 $$t; done
	$(MAKE) test-web

test-web web-test:
	cd packages/ze-ui && bun run test
	cd $(ZE_WEB) && bun run test

# ── Web app build ─────────────────────────────────────────────────────────────
.PHONY: web-build

web-build:
	cd $(ZE_WEB) && bun run build

# ── Code generation ───────────────────────────────────────────────────────────
.PHONY: codegen

codegen:
	bun run scripts/codegen.ts

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
