"""Controlled vocabulary for memory graph relationship predicates.

Predicates are uppercase strings so they read clearly in logs and DB rows.
Only extend this list when a concrete retrieval or audit use case demands it.
"""

# entity → fact: the entity is the subject the fact describes
DESCRIBES = "DESCRIBES"

# fact → episode: the episode is the source from which the fact was extracted
SOURCED_FROM = "SOURCED_FROM"

# episode → entity: the entity is mentioned in the episode
MENTIONS = "MENTIONS"

# event → entity: the entity participates in or is the target of the event
PARTICIPATES_IN = "PARTICIPATES_IN"

# procedure → task_state: the task is executing or recently executed the procedure
USES_PROCEDURE = "USES_PROCEDURE"

# task_state → goal: the task belongs to the goal execution
BELONGS_TO_GOAL = "BELONGS_TO_GOAL"

# event → fact: a durable learning extracted from a lived event
PROMOTES_TO = "PROMOTES_TO"

ALL_PREDICATES: frozenset[str] = frozenset(
    {
        DESCRIBES,
        SOURCED_FROM,
        MENTIONS,
        PARTICIPATES_IN,
        USES_PROCEDURE,
        BELONGS_TO_GOAL,
        PROMOTES_TO,
    }
)
