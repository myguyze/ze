# ADR: Dataclasses in domain code, Pydantic only at the API boundary

> **Status:** Accepted
> **Date:** 2023-11-01 (Phase 1)
> **Scope:** Every domain type across every package

---

## Context and Problem Statement

FastAPI encourages Pydantic models everywhere. The question is whether to use Pydantic
throughout Ze (types, stores, agents) or restrict it to the API layer. Using Pydantic
everywhere is the FastAPI default and requires no deliberate discipline to maintain.

---

## Decision Drivers

- Domain types should not carry serialisation, validation, or schema-generation logic —
  those are API-layer concerns
- `models.py` filename is too easily confused with ORM models; Ze has no ORM
- Pydantic's runtime validation machinery is unnecessary overhead for internal types
  that are only ever constructed by our own code
- Import graphs should be clean: domain packages should not import FastAPI or Pydantic
- `ze_sdk.*` is the plugin entry point — plugins must not need to know about the API
  serialisation layer

---

## Considered Options

1. **Pydantic everywhere** — `BaseModel` for all types, including domain types
2. **attrs** — third-party typed dataclass library with validators
3. **Stdlib dataclasses in domain, Pydantic only at API boundary**

---

## Decision Outcome

**Chosen option: stdlib dataclasses in domain, Pydantic only in `ze_api/api/schemas.py`.**

Domain types live in `<module>/types.py` as `@dataclass` classes. FastAPI request and
response schemas live in `ze_api/api/schemas.py` as Pydantic `BaseModel` subclasses.
The API layer translates between the two at the boundary.

### Positive Consequences

- Domain packages have no Pydantic dependency — clean import graph
- `types.py` filename makes it unambiguous these are domain types, not ORM models
- No accidental serialisation side effects when domain types are logged or stored
- Plugin authors only import `ze_sdk.*` — no exposure to FastAPI internals

### Negative Consequences / Trade-offs

- No runtime validation on internal types — a wrong type will raise at use, not at
  construction. Acceptable: internal code is trusted; validation happens at system
  boundaries (user input, OpenRouter responses).
- Translation layer between `@dataclass` and `BaseModel` is a small amount of boilerplate
  in the API layer.
- Enforcement is convention, not machine-checked — nothing stops a contributor
  importing `BaseModel` inside `ze_personal/`. Lint rules and code review are the gate.

---

## Pros and Cons of the Options

### Option 1 — Pydantic everywhere

**Pros:** One model definition does validation, serialisation, and OpenAPI schema
generation. FastAPI's natural idiom.

**Cons:** Pydantic leaks into every domain package. Domain types carry HTTP-era
concerns (field aliases, json_encoders). Import chains become hard to reason about.
Plugin authors must understand Pydantic to write domain types.

### Option 2 — attrs

**Pros:** Better than stdlib dataclasses (slots, validators, converters).

**Cons:** Another dependency; less familiar than stdlib; no practical advantage over
dataclasses for Ze's use case.

### Option 3 — Dataclasses + Pydantic at boundary

**Pros:** Clean separation of concerns; domain types are pure data; API layer owns
serialisation.

**Cons:** Requires discipline to enforce; small translation boilerplate.

---

## Links

- `ze_api/api/schemas.py` — Pydantic schemas (the only allowed location)
- Any `<module>/types.py` — canonical domain type location
