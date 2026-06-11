# ── Ze — project Makefile ─────────────────────────────────────────────────────

.DEFAULT_GOAL := help

ZE      := apps/ze-api
ZE_CORE := core/ze-core
ZE_APP  := apps/ze-app

# Flutter dev — server URL + API key from backend .env (skipped in app-build)
ZE_API_KEY_DEV := $(shell grep -E '^ZE_API_KEY=' $(ZE)/.env 2>/dev/null | cut -d= -f2- | tr -d '\r')
FLUTTER_DEV_DEFINES := --dart-define=ZE_DEV=true --dart-define=ZE_SERVER_URL=http://localhost:8000
ifneq ($(ZE_API_KEY_DEV),)
FLUTTER_DEV_DEFINES += --dart-define=ZE_API_KEY=$(ZE_API_KEY_DEV)
endif
FLUTTER_WEB_RUN := cd $(ZE_APP) && flutter run -d chrome $(FLUTTER_DEV_DEFINES)

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
	@echo "    app-get              Install Flutter app dependencies (flutter pub get)"
	@echo "    app-gen              Run Flutter code generation (freezed / riverpod / json)"
	@echo "    google-auth          One-time Google OAuth2 flow (Calendar + Gmail)"
	@echo "    generate-ze-api-key  Generate or refresh ZE_API_KEY in .env"
	@echo ""
	@echo "  Database"
	@echo "    db-up            Start Postgres via docker-compose"
	@echo "    db-down          Stop Postgres"
	@echo "    db-reset         Drop + recreate ze database and apply all migrations"
	@echo "    migrate          Apply all pending migrations (upgrade heads)"
	@echo "    migrate-down     Roll back one migration step"
	@echo "    migrate-status   Show current migration revision"
	@echo "    migrate-history  List all migrations"
	@echo "    migrate-stamp    Stamp existing DB to squashed heads (run once after squash)"
	@echo ""
	@echo "  Development"
	@echo "    dev              Start backend only (uvicorn --reload on :8000)"
	@echo "    app              Start Flutter app on macOS (connects to localhost:8000)"
	@echo "    app-web          Start Flutter app in Chrome (requires 'make dev' running)"
	@echo "    app-ios          Start Flutter app on iOS simulator"
	@echo "    dev-full         Start backend + Flutter web app in Chrome (Ctrl-C stops both)"
	@echo "    dev-eval         Start backend without background jobs (use before evals)"
	@echo "    logs             Tail the server log file (LOG_FILE=$(LOG_FILE))"
	@echo ""
	@echo "  App testing & quality"
	@echo "    app-test         Run Flutter unit tests"
	@echo "    app-analyze      Run flutter analyze"
	@echo "    app-build        Build Flutter macOS release bundle"
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
.PHONY: install app-get app-gen google-auth generate-ze-api-key

install:
	uv sync

app-get:
	cd $(ZE_APP) && flutter pub get

app-gen:
	cd $(ZE_APP) && flutter pub run build_runner build --delete-conflicting-outputs

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
	$(ZE_MIGRATE) upgrade

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
.PHONY: dev app app-web app-ios dev-full dev-eval logs

dev:
	LOG_DEV=true LOG_FILE=$(LOG_FILE) uv run uvicorn ze_api.api.app:app --reload --host 0.0.0.0 --port 8000

app:
	cd $(ZE_APP) && flutter run -d macos $(FLUTTER_DEV_DEFINES)

app-web:
	$(FLUTTER_WEB_RUN)

app-ios:
	cd $(ZE_APP) && flutter run -d iphone $(FLUTTER_DEV_DEFINES)

# Starts the backend in the background, waits for :8000 to be ready, then runs
# the Flutter web app in Chrome. Ctrl-C stops Flutter and kills the backend.
dev-full:
	@trap 'kill %1 2>/dev/null; exit 0' INT TERM; \
	LOG_DEV=true LOG_FILE=$(LOG_FILE) uv run uvicorn ze_api.api.app:app --reload --host 0.0.0.0 --port 8000 & \
	until nc -z localhost 8000 2>/dev/null; do sleep 1; done; \
	echo "Backend ready — starting Flutter app (Chrome)..."; \
	$(FLUTTER_WEB_RUN); \
	kill %1 2>/dev/null

dev-eval:
	PUBLIC_URL= LOG_DEV=true LOG_FILE=$(LOG_FILE) uv run uvicorn ze_api.api.app:app --reload --host 0.0.0.0 --port 8000

logs:
	tail -f $(LOG_FILE)

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
	uv run pytest \
		$(ZE)/tests \
		$(ZE_CORE)/tests \
		plugins/ze-personal/tests \
		plugins/ze-prospecting/tests \
		plugins/ze-email/tests \
		plugins/ze-calendar/tests \
		plugins/ze-news/tests \
		-q

# ── App testing & quality ─────────────────────────────────────────────────────
.PHONY: app-test app-analyze app-build

app-test:
	cd $(ZE_APP) && flutter test

app-analyze:
	cd $(ZE_APP) && flutter analyze

app-build:
	cd $(ZE_APP) && flutter build macos

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
