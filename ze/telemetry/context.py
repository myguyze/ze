from contextvars import ContextVar
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class CostContext:
    flow_type: str
    agent: str
    session_id: str | None = None


_CTX: ContextVar[CostContext | None] = ContextVar("ze_cost_ctx", default=None)


def set_flow_context(flow_type: str, session_id: str | None = None) -> None:
    current = _CTX.get()
    if current is not None:
        _CTX.set(replace(current, flow_type=flow_type, session_id=session_id))
    else:
        _CTX.set(CostContext(flow_type=flow_type, agent="unknown", session_id=session_id))


def set_agent_context(agent: str) -> None:
    current = _CTX.get()
    if current is not None:
        _CTX.set(replace(current, agent=agent))


def get_cost_context() -> CostContext:
    return _CTX.get() or CostContext(flow_type="unknown", agent="unknown")
