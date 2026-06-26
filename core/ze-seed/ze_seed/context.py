from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ze_seed.narrative.loader import PersonaNarrative, load_persona


@dataclass
class SeedContext:
    pool: Any
    memory_store: Any
    embedder: Any
    message_store: Any
    session_store: Any
    goal_store: Any | None = None
    persona_store: Any | None = None
    person_store: Any | None = None
    reminder_store: Any | None = None
    narrative: PersonaNarrative | None = None

    @classmethod
    def from_container(cls, container: Any) -> SeedContext:
        person_store = container._plugin_stores.get("person_store")
        reminder_store = container._plugin_stores.get("reminder_store")
        return cls(
            pool=container.pool,
            memory_store=container.memory_store,
            embedder=container.embedder,
            goal_store=container._plugin_stores.get("goal_store"),
            message_store=container.message_store,
            session_store=container.session_store,
            persona_store=container.persona_store,
            person_store=person_store,
            reminder_store=reminder_store,
            narrative=load_persona(),
        )
