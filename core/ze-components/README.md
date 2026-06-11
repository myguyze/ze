# ze-components

Server-driven UI component descriptors for Ze. Allows agents to emit structured component payloads that the Flutter client (`ze-app`) renders without requiring app updates.

## Responsibilities

| Module | What it provides |
|---|---|
| `schema.py` | JSON schema generation from Python dataclasses — used to build LLM tool schemas |
| `types.py` | Component descriptor dataclasses |
| `context.py` | Component context helpers |
| `tools.py` | Agent tool integration for emitting components |

## Dependencies

No Ze package dependencies. Pure Python — no third-party runtime dependencies.

## Concept

Agents call component tools during execution; the resulting descriptors are serialised and sent as a `components` field in the WebSocket message frame. The Flutter app deserialises and renders them inline with the text response.

```python
from ze_components.types import ComponentDescriptor

# An agent emits a component during its tool loop
descriptor = ComponentDescriptor(type="goal_card", props={"title": "...", "status": "active"})
```

## Code generation

Component schemas are generated from Python dataclasses:

```bash
make generate-components
```
