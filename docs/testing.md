# Testing

All tests run from the **repository root**. Every package has a `make test-<name>` target;
`make test-all` runs the full suite across all packages.

---

## Quick reference

| Target | Package | Runner |
|---|---|---|
| `make test` / `make test-api` | ze-api | pytest |
| `make test-core` | ze-core | pytest |
| `make test-agents` | ze-agents | pytest |
| `make test-plugin` | ze-plugin | pytest |
| `make test-sdk` | ze-sdk | pytest |
| `make test-proactive` | ze-proactive | pytest |
| `make test-memory` | ze-memory | pytest |
| `make test-automation` | ze-automation | pytest |
| `make test-onboarding` | ze-onboarding | pytest |
| `make test-correlation` | ze-correlation | pytest |
| `make test-browser` | ze-browser | pytest |
| `make test-notifications` | ze-notifications | pytest |
| `make test-components` | ze-components | pytest |
| `make test-eval` | ze-eval | pytest |
| `make test-google` | ze-google | pytest |
| `make test-personal` | ze-personal | pytest |
| `make test-email` | ze-email | pytest |
| `make test-calendar` | ze-calendar | pytest |
| `make test-prospecting` | ze-prospecting | pytest |
| `make test-news` | ze-news | pytest |
| `make test-web` / `make web-test` | ze-web | vitest |
| `make test-all` | all packages | pytest + vitest |

---

## Conventions

### Target naming

- Pattern: `make test-<short-name>` where `<short-name>` is the package name without the
  `ze-` prefix (`ze-personal` → `test-personal`, `ze-api` → `test-api`).
- `make test` is a shortcut for `make test-api` (the default CI gate).
- `make test-web` and `make web-test` are equivalent.

### Test layout

- Python packages: tests live in `<package>/tests/`, mirroring the package structure.
- React app: tests live in `apps/ze-web/src/**/*.test.ts(x)`.
- Run from the repo root — never `cd` into a package to run tests in CI or docs.

### Default pytest invocation

Every Python `test-*` target runs:

```bash
uv run pytest <package>/tests -m 'not slow' -q
```

Pass `SLOW=1` to include slow tests (embedding model load in ze-core):

```bash
make test-core SLOW=1
```

`make test-all` sets `SLOW=1` automatically and runs every package target plus `test-web`.

### Direct pytest (fallback)

When filtering to a single file or test name:

```bash
uv run pytest core/ze-memory/tests/test_store_writes.py -q
uv run pytest apps/ze-api/tests -k test_health -q
```

---

## What to run when

| Change location | Run |
|---|---|
| Any Python package | `make test-<name>` for that package |
| Multiple packages / unsure | `make test-all` |
| Before opening a PR | `make test`, `make lint`, and `make test-web` if ze-web changed |
| Embedding / routing internals | `make test-core SLOW=1` or `make test-all` |

---

## Adding a new package

1. Create `<package>/tests/` with at least one test module.
2. Add a `test-<short-name>` target to the Makefile (keep the list in `TEST_PY_PACKAGES` in sync).
3. Document the target in the package README `## Testing` section.
4. Add a row to the table in this file.
