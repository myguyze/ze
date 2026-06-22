# plugins/

Domain plugin packages. Each plugin implements `ZePlugin` and contributes agents,
stores, background jobs, and migrations to the Ze graph. Plugins are discovered
automatically via `[project.entry-points."ze.plugins"]` in each package's
`pyproject.toml` — no manual registration in `ze-api`.

**Rule:** plugins may import from `core/` (via `ze-sdk`) and `integrations/` but never from `apps/`.

Package READMEs follow [docs/package-readme-template.md](../docs/package-readme-template.md).
Tests run from the repo root via `make test-<short-name>`. See [docs/testing.md](../docs/testing.md).

---

## Packages

| Package | Description |
|---------|-------------|
| [ze-personal](ze-personal/) | Personal-assistant domain — goals, workflows, persona, contacts, research and companion agents |
| [ze-email](ze-email/) | Gmail channel and email agent |
| [ze-calendar](ze-calendar/) | Calendar, reminders, and timezone domain |
| [ze-prospecting](ze-prospecting/) | Autonomous prospect research, campaign store, outreach drafting |
| [ze-news](ze-news/) | News ingestion, personalised ranking, credibility analysis, news agent |
| [ze-finance](ze-finance/) | Finance domain — portfolio positions, bank transactions, spending summaries, proactive P&L alerts |

## Dependency graph

```
ze-personal    ←  ze-sdk
ze-email       ←  ze-sdk, ze-google, ze-personal
ze-calendar    ←  ze-sdk, ze-google, ze-personal
ze-prospecting ←  ze-sdk, ze-browser, ze-personal
ze-news        ←  ze-sdk, ze-memory
```

## Adding a new plugin

1. Write a spec in `specs/phases/` first.
2. Create the package directory here: `plugins/ze-<name>/`.
3. Add a [README](ze-personal/README.md) following the template in `docs/package-readme-template.md` (include **Role in Ze** with key features and integration details).
4. Implement `ZePlugin` in `plugin.py` and declare the entry point in `pyproject.toml`:
   ```toml
   [project.entry-points."ze.plugins"]
   ze_myplugin = "ze_myplugin.plugin:MyPlugin"
   ```
5. Add the package to `apps/ze-api/pyproject.toml` dependencies.
6. Override plugin hooks as needed: `agent_module_paths()`, `memory_policies()`,
   `checkpoint_serde_modules()`, `rest_stores()`, `register_proactive_jobs()`.
7. If the plugin constructor needs a new shared service type, add it to `plugin_deps`
   in `apps/ze-api/ze_api/container.py` (see [docs/extending-ze.md](../docs/extending-ze.md)).
8. See [docs/adding-an-agent.md](../docs/adding-an-agent.md) and
   [docs/package-architecture.md](../docs/package-architecture.md) for the full checklist.

## Plugin contract

```python
class ZePlugin(ABC):
    def agent_module_paths(self) -> list[str]: ...
    def memory_policies(self) -> dict[str, MemoryRetrievalPolicy]: ...
    def checkpoint_serde_modules(self) -> tuple[str, ...]: ...
    def rest_stores(self) -> dict[str, Any]: ...
    def register_proactive_jobs(self, scheduler, settings, *, consolidation_enabled=True): ...
    # … graph extension hooks
```

A plugin earns its own package when it has its own Postgres tables, contributes at
least one agent or job, and can be disabled without breaking the rest of Ze.
