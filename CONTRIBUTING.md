# Contributing to Ze

Ze is a solo-maintained personal project. Contributions are welcome but the bar is practical: changes should be clean, tested, and easy to reason about. This guide covers everything you need to go from zero to a merged PR.

---

## Getting started

**Prerequisites:** Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker.

```bash
git clone https://github.com/joaoajmatos/ze.git
cd ze

make install       # install all packages in dev mode via uv
make db-up         # start Postgres (Docker)
make migrate       # apply all migrations

cp apps/ze-api/.env.example apps/ze-api/.env
# Fill in OPENROUTER_API_KEY, ZE_API_KEY, DATABASE_URL at minimum.

make dev           # API + WebSocket on :8000
make web-install   # React web app deps (Bun)
make web           # React web app on :5173
# or: make dev-full   # backend + web app together
```

---

## Workflow

1. **Fork** the repo and create a branch from `main`.
   Branch names: `feat/short-description`, `fix/short-description`, `chore/short-description`.

2. **Make your changes.** Keep each PR focused — one feature or fix per PR.

3. **Run checks** before pushing:
   ```bash
   make check       # ruff + ze-web tsc build — mirrors CI lint gates
   make lint-web    # optional: ESLint / FSD boundaries when editing ze-web
   make test        # ze-api (skips slow) — must pass
   make test-web    # vitest — must pass if you changed ze-web
   make test-all    # optional, all packages including slow
   ```
   Install git hooks once so commits and pushes are checked automatically:
   ```bash
   make hooks       # pre-commit: staged ruff/tsc; pre-push: make check
   ```
   Bypass in an emergency: `SKIP=1 git commit` or `SKIP=1 git push`.
   Per-package targets: `make test-<name>` from repo root. Full list: [docs/testing.md](docs/testing.md).

4. **Open a PR** against `main`. The PR description should say *why* the change is needed,
   not just what it does.

5. PRs that break tests or lint will not be merged.

---

## Code conventions

These are enforced consistently across the codebase — please match them.

### Python

- **Domain types**: dataclasses in `types.py`. Never use Pydantic models outside `ze_api/api/schemas.py`.
- **File naming**: `types.py` everywhere (not `models.py`).
- **Dependency injection**: constructor injection in all classes. `FastAPI Depends()` only in `ze_api/api/`.
- **Logging**: `get_logger(__name__)` from structlog. No `print()`, no stdlib `logging`.
- **Errors**: subclass `ZeError` from `ze_core/errors.py` or `ze_api/errors.py`. Never raise bare `Exception` or `ValueError` in domain code.
- **Async**: all I/O is async. Fire-and-forget via `asyncio.create_task()`. Never `asyncio.run()` inside a running loop.
- **Comments**: write none by default. Only add one when the *why* is non-obvious (a hidden constraint, a subtle invariant, a workaround for a specific external bug).

### Tests

- Tests mirror `ze/` structure under `tests/`.
- `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` needed.
- No real DB in unit tests — mock asyncpg pools with `AsyncMock`.
- No real LLM calls — mock `client.complete` and `client.stream`.
- Slow tests (embedding model load): mark with `@pytest.mark.slow`.

### Commits

Write commit messages in the imperative: **Add X**, **Fix Y**, **Remove Z**.
Keep the subject line under 72 characters. If the *why* isn't obvious from the diff, add a short body paragraph.

---

## Adding an agent

See [docs/adding-an-agent.md](docs/adding-an-agent.md) for the full authoring guide. The short version:

1. Write a spec in `specs/phases/` first (use `specs/TEMPLATE.md`).
2. Create the agent in the appropriate package under `agents/`, decorated with `@agent`, subclassing `BaseAgent`.
3. Write tests in `tests/agents/<name>/`.
4. Wire it in `ze_api/container.py`.

---

## Adding a database migration

```bash
# Edit the new SQL file directly in apps/ze-api/migrations/versions/
# Follow the existing naming convention: NNN_description.py
make migrate
```

Migrations are raw SQL (no ORM). Keep them idempotent where possible.

---

## What not to send

- Changes to `.env` or any file containing secrets.
- New dependencies added without a clear reason — `uv add` changes to `pyproject.toml` should be justified in the PR description.
- Refactors unrelated to the stated goal of the PR.
- Comments that describe *what* the code does rather than *why*.

---

## Questions

Open a [GitHub issue](https://github.com/joaoajmatos/ze/issues) for bugs or feature requests.
For design questions, check `specs/` first — most decisions are already written up there.
