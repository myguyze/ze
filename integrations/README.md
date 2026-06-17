# integrations/

External service integration packages. Each package wraps a third-party API or
protocol and exposes a clean interface for Ze packages to consume.

**Rule:** an `integrations/` package has no Ze domain knowledge and no dependency
on `plugins/` or `apps/`. It depends only on third-party libraries (and optionally
other `integrations/` or `core/` packages).

---

## Packages

| Package | Description |
|---------|-------------|
| [ze-google](ze-google/) | Google OAuth2 credentials and service client factories (Calendar, Gmail) |

## Dependency graph

```
ze-google  ←  no ze deps
```

## Where new code goes

| New code | Package |
|----------|---------|
| New Google service client factory | `ze-google` |
| New broker / trading API client | create `ze-<broker>/` here |
| Any other third-party API wrapper | create `ze-<service>/` here |

Integration packages are consumed by `plugins/` (which have domain knowledge) and
by `apps/ze-api` (which wires everything together).
