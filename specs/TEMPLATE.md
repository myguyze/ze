# Spec Templates

Three templates — pick the right one:

| Spec type | Template | When to use |
|-----------|----------|-------------|
| Feature / phase | [TEMPLATE-phase.md](TEMPLATE-phase.md) | Anything in `phases/` — new capability, refactor, package extraction |
| Architecture decision | [TEMPLATE-adr.md](TEMPLATE-adr.md) | Anything in `arch/` — a choice between options with lasting consequences |
| Core module | [TEMPLATE-core.md](TEMPLATE-core.md) | Anything in `core/` — a new Ze infrastructure module |

## Which template?

- If you are shipping a feature → `TEMPLATE-phase.md`
- If you are recording a design choice that affects multiple phases or packages → `TEMPLATE-adr.md`
- If you are speccing a new `core/ze-*` module in isolation → `TEMPLATE-core.md`

When in doubt, start with `TEMPLATE-phase.md`. You can always extract the
architectural decisions section into a standalone ADR later.

## Rules

1. **Required sections** (phase): Summary, Goals, Non-Goals, Alternatives Considered, Definition of Done.
2. **Required sections** (ADR): Context and Problem Statement, Considered Options, Decision Outcome.
3. **Status is authoritative in the spec header.** The README table is an index — update both,
   but if they diverge, the spec header wins.
4. Resolve all Open Questions (or explicitly defer them with a date) before setting status → Done.
5. Move recurring patterns or cross-cutting decisions to `arch/` rather than duplicating them
   in phase specs.
