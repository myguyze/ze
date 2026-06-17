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

## Integration contract

Every credentials class in an integration package must satisfy the `ZeIntegration`
protocol (defined in `ze_agents.integration`) **structurally** — no import required:

```python
@classmethod
def from_settings(cls, settings) -> "MyCredentials | None":
    """Read named attributes from settings (duck-typed).
    Return None when any required env var is absent — never raise.
    """
    if not settings.my_service_api_key:
        return None
    return cls(api_key=settings.my_service_api_key)
```

Rules:
1. **No Ze imports** — integration packages have zero Ze dependencies.
2. **Duck-typed settings** — read named attributes; never import `ze_api.settings.Settings`.
   Add required env var fields to `ze_api/settings.py` as `Optional[str] = None`.
3. **Return `None` when unconfigured** — plugins enforce required credentials in `startup()`.
4. **Synchronous** — async init (token exchange, connection warmup) goes in `plugin.startup()`.
5. **Thread/task safe** — credentials objects are singletons shared across async tasks.

Plugins declare which integration types they need via `ZePlugin.integration_types()`.
The bootstrapper deduplicates, calls `from_settings` once per type, and injects the
result into the plugin DI map automatically — no changes to `container.py` needed.
