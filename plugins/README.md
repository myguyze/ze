# plugins/

Domain plugin packages. Each plugin implements `ZePlugin` and contributes agents,
stores, background jobs, and migrations to the Ze graph. Plugins are registered in
`apps/ze-api/ze_api/container.py` and can be toggled independently.

**Rule:** plugins may import from `core/` but never from `apps/`.

---

## Packages

| Package | Description |
|---------|-------------|
| [ze-personal](ze-personal/) | Personal-assistant domain — goals, workflows, persona, contacts, research and companion agents |
| [ze-email](ze-email/) | Gmail channel and email agent |
| [ze-calendar](ze-calendar/) | Calendar, reminders, and timezone domain |
| [ze-prospecting](ze-prospecting/) | Autonomous prospect research, campaign store, outreach drafting |
| [ze-news](ze-news/) | News ingestion, personalised ranking, credibility analysis, news agent |
| [ze-finance](ze-finance/) | Finance domain *(in progress)* |
| [ze-legal](ze-legal/) | Legal domain *(in progress)* |

## Dependency graph

```
ze-personal    ←  ze-core, ze-memory
ze-email       ←  ze-core, ze-google, ze-personal
ze-calendar    ←  ze-core, ze-google, ze-personal
ze-prospecting ←  ze-core, ze-browser, ze-personal
ze-news        ←  ze-core, ze-memory
```

## Adding a new plugin

1. Write a spec in `specs/phases/` first.
2. Create the package directory here: `plugins/ze-<name>/`.
3. Implement `ZePlugin` in `plugin.py`.
4. Register it in `apps/ze-api/ze_api/container.py`.
5. See [docs/adding-an-agent.md](../docs/adding-an-agent.md) and
   [docs/package-architecture.md](../docs/package-architecture.md) for the full checklist.

## Plugin contract

```python
class ZePlugin(ABC):
    def agents(self) -> list[type[BaseAgent]]: ...
    def jobs(self) -> list[ProactiveJob]: ...
    def migrations_path(self) -> Path | None: ...
    def agent_module_paths(self) -> list[str]: ...
    # … graph extension hooks
```

A plugin earns its own package when it has its own Postgres tables, contributes at
least one agent or job, and can be disabled without breaking the rest of Ze.
