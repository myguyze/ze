# Progress Messages — Spec

## Implementation Status

| Feature | Status |
|---------|--------|
| `ProgressReporter` — emit + delete | ✅ Done |
| `ProgressTranslations` — key → locale string | ✅ Done |
| Locale config (`persona.locale` in config.yaml) | ✅ Done |
| `BaseAgent.emit()` — agent-facing helper | ✅ Done |
| All agents wired (companion, research, calendar, email, workflow, reminders) | ✅ Done |
| `execution.py` injects reporter from config | ✅ Done |

## Purpose

Give agents a first-class channel to push ephemeral status messages to the user
during execution. Messages appear in Telegram as the agent works, are collected
into a bucket, and are deleted atomically when the final response arrives — leaving
a clean conversation with no trace of the intermediate chatter.

Agents emit **translation keys** (e.g. `"research.searching"`), not raw strings.
The `ProgressReporter` resolves keys to localized text at emit time, so agents
never carry locale logic. The active locale is set once in `config.yaml` under
`persona.locale`.

This replaces the routing-level status message added alongside multimodal input
with something more expressive: agents own their messaging, can send multiple
messages, and can time them to meaningful moments in their execution.

---

## Out of Scope

- Persistent status messages (all are ephemeral — deleted on completion).
- Streaming token output via message edits.
- Progress bars or percentage indicators.
- Status messages from graph infrastructure nodes (routing, memory, capability
  check). Only agents emit progress messages.
- Error messages via this channel — those use the existing error path.
- Right-to-left layout adjustments or locale-specific emoji conventions.

---

## Repository Layout

```
ze/
├── progress/
│   ├── __init__.py
│   ├── reporter.py         # ProgressReporter
│   └── translations.py     # ProgressTranslations — loads + resolves keys
├── agents/
│   ├── base.py             # add emit() helper
│   ├── types.py            # add reporter field to AgentContext
│   ├── research/agent.py   # emit "research.searching", "research.summarising"
│   ├── companion/agent.py  # emit "companion.thinking"
│   ├── calendar/agent.py   # emit "calendar.reading" or "calendar.writing"
│   ├── email/agent.py      # emit "email.reading" or "email.drafting"
│   └── workflow/agent.py   # emit "workflow.reading" or "workflow.managing"
├── orchestration/
│   └── nodes/
│       ├── context.py      # inject reporter from configurable into AgentContext
│       └── execution.py    # propagate reporter to subtask AgentContexts
├── telegram/
│   └── bot.py              # create reporter + bucket, watcher task, cleanup
└── container.py            # load ProgressTranslations, inject into ZeBot
config/
└── locales/
    ├── en.yaml             # English (canonical)
    └── pt.yaml             # Portuguese (example additional locale)
```

---

## Locale Configuration

`config/config.yaml` — add to the `persona` block:

```yaml
persona:
  traits:
    - direct
    - warm
    - concise
  verbosity: concise
  custom_instructions: ""
  locale: en              # NEW — ISO 639-1 code; selects config/locales/<locale>.yaml
```

`locale` defaults to `"en"` if absent. The value is read once at startup by
`ProgressTranslations.load()`.

---

## Translation Files

`config/locales/en.yaml` — the canonical file; all other locales must cover the
same key tree. Values are either a single string or a list of variants (one is
chosen at random on each emit).

```yaml
research:
  searching:
    - "🔍 Searching the web..."
    - "🌐 Looking that up..."
    - "📰 Digging through sources..."
    - "🕵️ Tracking that down..."
  summarising:
    - "📰 Summarising results..."
    - "📚 Pulling this together..."
    - "✍️ Writing up what I found..."

companion:
  thinking:
    - "💭 Thinking..."
    - "🧠 Working through this..."
    - "✍️ Drafting a response..."
    - "🤔 Mulling it over..."

calendar:
  reading:
    - "📅 Checking your calendar..."
    - "🗓️ Looking at your schedule..."
    - "📅 Let me check..."
  writing:
    - "📅 Updating your calendar..."
    - "🗓️ Making that change..."

email:
  reading:
    - "📧 Checking your inbox..."
    - "✉️ Searching your emails..."
    - "📬 Looking through your mail..."
  drafting:
    - "✉️ Drafting that email..."
    - "📨 Composing your message..."
    - "✍️ Writing that up..."

workflow:
  reading:
    - "⚙️ Checking your workflows..."
    - "📋 Looking up your tasks..."
  managing:
    - "⚙️ Setting that up..."
    - "🔧 Managing that for you..."
    - "⚙️ On it..."
```

`config/locales/pt.yaml` — same structure, Portuguese strings:

```yaml
research:
  searching:
    - "🔍 A pesquisar na web..."
    - "🌐 Já a ver isso..."
    - "📰 A procurar fontes..."
  summarising:
    - "📰 A resumir os resultados..."
    - "📚 A compilar a informação..."

companion:
  thinking:
    - "💭 A pensar..."
    - "🧠 A trabalhar nisso..."
    - "🤔 Deixa-me refletir..."

calendar:
  reading:
    - "📅 A verificar o teu calendário..."
    - "🗓️ A ver a tua agenda..."
  writing:
    - "📅 A atualizar o teu calendário..."

email:
  reading:
    - "📧 A verificar a tua caixa de entrada..."
    - "✉️ A procurar nos teus emails..."
  drafting:
    - "✉️ A redigir o email..."
    - "📨 A compor a mensagem..."

workflow:
  reading:
    - "⚙️ A verificar os teus workflows..."
  managing:
    - "⚙️ A configurar isso..."
    - "🔧 A tratar disso..."
```

---

## `ProgressTranslations`

`ze/progress/translations.py`

```python
import random
from pathlib import Path

import yaml

from ze.logging import get_logger

log = get_logger(__name__)


class ProgressTranslations:
    def __init__(self, data: dict, fallback: dict) -> None:
        self._data = data
        self._fallback = fallback

    @classmethod
    def load(cls, locale: str, config_dir: Path) -> "ProgressTranslations":
        en = cls._load_file(config_dir / "locales" / "en.yaml")
        if locale == "en":
            return cls(data=en, fallback=en)
        target = cls._load_file(config_dir / "locales" / f"{locale}.yaml")
        return cls(data=target, fallback=en)

    def resolve(self, key: str, **kwargs: str) -> str | None:
        """
        Resolve a dotted key to a localized string.
        Falls back to English if the key is absent from the active locale.
        Returns None if the key is unknown in both — callers skip the emit.
        """
        text = self._lookup(self._data, key) or self._lookup(self._fallback, key)
        if text is None:
            log.warning("progress_key_missing", key=key)
            return None
        return text.format(**kwargs) if kwargs else text

    @staticmethod
    def _load_file(path: Path) -> dict:
        try:
            return yaml.safe_load(path.read_text()) or {}
        except Exception as exc:
            log.warning("progress_locale_load_failed", path=str(path), error=str(exc))
            return {}

    @staticmethod
    def _lookup(d: dict, key: str) -> str | None:
        val: object = d
        for part in key.split("."):
            if not isinstance(val, dict) or part not in val:
                return None
            val = val[part]
        if isinstance(val, list):
            return random.choice(val) if val else None
        if isinstance(val, str):
            return val
        return None
```

---

## `ProgressReporter`

`ze/progress/reporter.py`

```python
import asyncio

from ze.progress.translations import ProgressTranslations


class ProgressReporter:
    """
    Passed into AgentContext. Agents call emit(key) to push a localized status
    message. The bot layer drains the queue and sends Telegram messages.
    """

    def __init__(self, queue: asyncio.Queue, translations: ProgressTranslations) -> None:
        self._queue = queue
        self._translations = translations

    async def emit(self, key: str, **kwargs: str) -> None:
        """Resolve key to a localized string and enqueue it. No-op if key unknown."""
        text = self._translations.resolve(key, **kwargs)
        if text is None:
            return
        try:
            self._queue.put_nowait(text)
        except asyncio.QueueFull:
            pass
```

The queue is unbounded so multiple rapid emits never block the agent.

---

## `AgentContext` Extension

`ze/agents/types.py`

```python
from ze.progress.reporter import ProgressReporter   # TYPE_CHECKING import to avoid circularity if needed

@dataclass
class AgentContext:
    session_id: str
    prompt: str
    intent: str
    gate_decision: GateDecision = GateDecision.EXECUTE
    memory: MemoryContext = field(default_factory=MemoryContext)
    tool_calls: list[ToolCall] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    model: str | None = None
    reporter: ProgressReporter | None = None   # NEW
```

`reporter` is `None` by default so all existing agent tests need no changes.

---

## `BaseAgent` Helper

`ze/agents/base.py`

```python
async def emit(self, ctx: AgentContext, key: str, **kwargs: str) -> None:
    """Emit a localized progress message if a reporter is attached."""
    if ctx.reporter is not None:
        await ctx.reporter.emit(key, **kwargs)
```

---

## Per-Agent Emit Points

Each agent emits at transitions that represent meaningful work. The key is the
dotted path into the locale YAML.

```python
# research/agent.py
async def run(self, ctx: AgentContext) -> AgentResult:
    await self.emit(ctx, "research.searching")
    search_tc = await self.call_tool("web_search", ctx, ...)

    await self.emit(ctx, "research.summarising")
    response = await self._client.complete(...)
```

```python
# companion/agent.py
async def run(self, ctx: AgentContext) -> AgentResult:
    await self.emit(ctx, "companion.thinking")
    response = await self._client.complete(...)
```

```python
# calendar/agent.py
async def run(self, ctx: AgentContext) -> AgentResult:
    key = "calendar.writing" if ctx.intent in ("create", "update", "delete") else "calendar.reading"
    await self.emit(ctx, key)
    ...
```

```python
# email/agent.py
async def run(self, ctx: AgentContext) -> AgentResult:
    key = "email.drafting" if ctx.intent in ("create", "update") else "email.reading"
    await self.emit(ctx, key)
    ...
```

```python
# workflow/agent.py
async def run(self, ctx: AgentContext) -> AgentResult:
    key = "workflow.managing" if ctx.intent == "manage" else "workflow.reading"
    await self.emit(ctx, key)
    ...
```

---

## Parameterised Messages (optional)

Keys may use `{name}` placeholders for dynamic content:

```yaml
# en.yaml
research:
  summarising_n: "📰 Summarising {count} results..."
```

```python
await self.emit(ctx, "research.summarising_n", count=str(len(results)))
```

`ProgressTranslations.resolve()` calls `str.format(**kwargs)` only when kwargs are
provided. Agents that do not need dynamic content pass no kwargs.

---

## Orchestration Layer Changes

### `ze/orchestration/nodes/context.py`

`fetch_context` reads `reporter` from `config["configurable"]` and attaches it:

```python
reporter = config["configurable"].get("reporter")
agent_context = AgentContext(
    ...
    reporter=reporter,
)
```

### `ze/orchestration/nodes/execution.py`

`_execute_single` and `_execute_compound` copy `reporter` from `base_ctx` into
each subtask context:

```python
ctx = AgentContext(
    ...
    reporter=base_ctx.reporter,   # same reporter → same bucket for compound tasks
)
```

---

## Bot Layer

`ze/telegram/bot.py` — `_run_graph()`

```python
async def _run_graph(self, chat_id: int, state: dict) -> None:
    config = self._make_config(chat_id)

    progress_queue: asyncio.Queue = asyncio.Queue()
    reporter = ProgressReporter(progress_queue, self._translations)
    config["configurable"]["reporter"] = reporter

    message_bucket: list[int] = []

    async def _progress_watcher() -> None:
        try:
            while True:
                text = await progress_queue.get()
                msg = await self._bot.send_message(chat_id, text)
                message_bucket.append(msg.message_id)
        except asyncio.CancelledError:
            pass

    watcher_task = asyncio.create_task(_progress_watcher())
    typing_task  = asyncio.create_task(self._keep_typing(chat_id))

    try:
        final_state = await self._graph.ainvoke(state, config)
    except Exception as exc:
        ...
        return
    finally:
        typing_task.cancel()
        watcher_task.cancel()
        await asyncio.gather(watcher_task, return_exceptions=True)
        for msg_id in message_bucket:
            try:
                await self._bot.delete_message(chat_id, msg_id)
            except Exception:
                pass
```

`ZeBot` receives `translations: ProgressTranslations` as a constructor argument,
injected by `container.py`.

---

## Container Changes

`ze/container.py`

```python
from ze.progress.translations import ProgressTranslations

translations = ProgressTranslations.load(
    locale=settings.persona_config.get("locale", "en"),
    config_dir=settings.config_dir,
)

ze_bot = ZeBot(
    ...
    translations=translations,
)
```

---

## Removing the Routing-Level Status

The routing-level `status_queue` in `embed_route` and the `_pick_status` / `_STATUS`
constants in `bot.py` are removed. Agents now own all messaging through this
mechanism. The routing node reverts to its form before the interim implementation.

This is a net simplification: one mechanism, one locale, one place to add strings.

---

## Timing

Status messages are sent by the watcher task concurrently with graph execution.
`emit()` is non-blocking (queue put). Deletion runs before `_send_response`.
The user sees: status messages appear → all disappear → final response arrives.

---

## Testing

- `ProgressTranslations.resolve()`: known key returns a string from the correct
  locale; unknown key returns `None` with a warning; list values are drawn randomly.
- `ProgressTranslations.load()`: missing locale file falls back to English without
  raising.
- `ProgressTranslations.resolve()` with kwargs: placeholder substitution applied.
- `ProgressReporter.emit()`: resolved text lands in the queue.
- `ProgressReporter.emit()` with unknown key: queue remains empty (no error).
- `BaseAgent.emit()` with `reporter=None`: no error raised.
- `BaseAgent.emit()` with a mock reporter: `reporter.emit(key)` called with the
  correct key.
- `fetch_context` with `reporter` in configurable: `agent_context.reporter` is set.
- `_execute_single` propagates `base_ctx.reporter` to the subtask `AgentContext`.
- Bot layer watcher: emit two keys; assert two messages sent; assert two IDs in
  bucket; assert both deleted in the `finally` block.
- Bot layer error path: graph raises; assert cleanup runs and bucket is drained.

---

## Open Questions

All resolved.

- **Why keys, not raw strings?** Agents must not carry locale logic. A key is a
  stable contract; the string is a locale detail.
- **Why YAML, not Python dicts?** The locale files are user-editable content, not
  code. YAML allows non-engineers to add a locale without touching Python.
- **Why `config/locales/` not `ze/progress/locales/`?** Locale files are
  configuration, not package data. They live alongside `config.yaml`.
- **What if a locale file is missing?** `_load_file` catches the exception and
  returns `{}`. `resolve()` falls through to the English fallback. Ze starts
  normally; a warning is logged.
- **Why unbounded queue?** Agents emit at most 2-3 messages per run. Bounding
  adds backpressure complexity with no practical benefit.
