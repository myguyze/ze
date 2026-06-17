# ze-components

Server-driven UI component descriptors for Ze. Allows agents to emit structured component payloads that the React web client (`ze-web`) renders without requiring app updates.

## Role in Ze

Text-only responses aren't enough for structured data — goal cards, confirmation forms, metric dashboards, timelines. Agents emit component descriptors during their tool loop; `ze-web` renders them inline with the chat response, so new UI patterns can ship from the backend without a frontend deploy.

### Key features

- Typed component descriptors (cards, forms, tables, timelines, metrics, confirmations)
- JSON schema generation from Python dataclasses for LLM tool schemas
- Code generation pipeline — `make generate-components` produces schemas and TypeScript types

### Integration

Agents call component tools during execution. A harness hook in `ze-api` collects descriptors from the agentic loop and attaches them to the WebSocket message frame's `components` field. `ze-web`'s `ComponentRenderer` deserialises and renders them.

## Responsibilities

| Module | What it provides |
|---|---|
| `schema.py` | JSON schema generation from Python dataclasses — used to build LLM tool schemas |
| `types.py` | Component descriptor dataclasses |
| `context.py` | Component context helpers |
| `tools.py` | Agent tool integration for emitting components |

## Dependencies

No Ze package dependencies. Pure Python — no third-party runtime dependencies.

## Usage

Agents call component tools during execution; the resulting descriptors are serialised and sent as a `components` field in the WebSocket message frame.

```python
from ze_components.types import ComponentDescriptor

descriptor = ComponentDescriptor(type="goal_card", props={"title": "...", "status": "active"})
```

## Code generation

Component schemas are generated from Python dataclasses:

```bash
make generate-components
```

TypeScript types for the web client are generated alongside the JSON schema.

## Testing

From the repo root:

```bash
make test-components
```

See [docs/testing.md](../../docs/testing.md).
