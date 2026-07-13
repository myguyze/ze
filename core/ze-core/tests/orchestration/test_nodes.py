import asyncio
import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock

from ze_agents.types import AgentContext, AgentResult
from ze_core.capability.gate import CapabilityGate
from ze_agents.types import GateDecision
from ze_agents.errors import AgentTimeoutError
from ze_memory.retriever import PostgresMemoryStore as MemoryStore
from ze_memory.types import Fact, MemoryContext
from ze_core.orchestration.nodes import context, execution, memory, routing
from ze_core.orchestration.nodes.execution import await_confirmation, capability_check
from ze_core.orchestration.nodes.memory import synthesize
from ze_core.orchestration.nodes.routing import embed_route
from ze_core.routing.types import RoutingEnvelope, SubTask
from tests.support.settings import make_settings


# ── Fixtures ──────────────────────────────────────────────────────────────────


def make_envelope(
    agent="research",
    intent="read",
    is_compound=False,
    subtasks=None,
) -> RoutingEnvelope:
    if subtasks is None:
        subtasks = [SubTask(agent=agent, intent=intent, prompt="test prompt")]
    return RoutingEnvelope(
        primary_agent=subtasks[0].agent,
        confidence=0.9,
        score_gap=0.3,
        routing_method="embedding",
        is_compound=is_compound,
        subtasks=subtasks,
        requires_synthesis=is_compound,
    )


def base_state(**overrides) -> dict:
    defaults: dict = {
        "prompt": "find AI news",
        "session_id": "s1",
        "session_overrides": {},
        "envelope": make_envelope(),
        "memory_context": None,
        "agent_context": None,
        "gate_decision": None,
        "agent_result": None,
        "subtask_results": [],
        "pending_confirmation": False,
        "final_response": None,
        "error": None,
    }
    defaults.update(overrides)
    return defaults


def make_mock_embedder():
    embedder = MagicMock()
    embedder.encode = MagicMock(return_value=np.zeros(384))
    return embedder


def make_persona_store():
    store = AsyncMock()
    store.get_active = AsyncMock(
        return_value={"traits": ["direct"], "verbosity": "concise", "dials": {}}
    )
    return store


def make_config(
    router=None,
    memory_store=None,
    capability_gate=None,
    settings=None,
    openrouter_client=None,
    embedder=None,
    persona_store=None,
) -> dict:
    return {
        "configurable": {
            "router": router or MagicMock(),
            "memory_store": memory_store or AsyncMock(spec=MemoryStore),
            "persona_store": persona_store or make_persona_store(),
            "capability_gate": capability_gate or MagicMock(spec=CapabilityGate),
            "settings": settings or make_settings(),
            "openrouter_client": openrouter_client or AsyncMock(),
            "embedder": embedder or make_mock_embedder(),
        }
    }


# ── routing.embed_route ───────────────────────────────────────────────────────


async def test_embed_route_sets_envelope():
    mock_router = AsyncMock()
    mock_router.route = AsyncMock(return_value=make_envelope())
    cfg = make_config(router=mock_router)
    result = await embed_route(base_state(), cfg)
    assert "envelope" in result
    assert result["envelope"].primary_agent == "research"


async def test_embed_route_calls_router_with_prompt_and_session():
    mock_router = AsyncMock()
    mock_router.route = AsyncMock(return_value=make_envelope())
    cfg = make_config(router=mock_router)
    state = base_state(prompt="latest AI", session_id="sess-42")
    await embed_route(state, cfg)
    mock_router.route.assert_awaited_once_with(prompt="latest AI", session_id="sess-42")


# ── context.fetch_context ─────────────────────────────────────────────────────


async def test_fetch_context_returns_memory_context():
    store = AsyncMock(spec=MemoryStore)
    store.retrieve = AsyncMock(return_value=MemoryContext())
    cfg = make_config(memory_store=store)
    result = await context.fetch_context(base_state(), cfg)
    assert result["memory_context"] is not None
    assert isinstance(result["memory_context"], MemoryContext)


async def test_fetch_context_returns_agent_context():
    store = AsyncMock(spec=MemoryStore)
    store.retrieve = AsyncMock(return_value=MemoryContext())
    cfg = make_config(memory_store=store)
    result = await context.fetch_context(base_state(prompt="hello"), cfg)
    assert result["agent_context"].prompt == "hello"
    assert result["agent_context"].session_id == "s1"


async def test_fetch_context_passes_memory_to_agent_context():
    memory_ctx = MemoryContext(
        facts=[Fact(predicate="name", object_text=None, object_id=None, value="Alice")]
    )
    store = AsyncMock(spec=MemoryStore)
    store.retrieve = AsyncMock(return_value=memory_ctx)
    cfg = make_config(memory_store=store)
    result = await context.fetch_context(base_state(), cfg)
    assert result["agent_context"].memory.facts[0].value == "Alice"


# ── execution.capability_check ────────────────────────────────────────────────


async def test_capability_check_execute():
    gate = MagicMock(spec=CapabilityGate)
    gate.evaluate.return_value = GateDecision.EXECUTE
    cfg = make_config(capability_gate=gate)
    result = await capability_check(base_state(), cfg)
    assert result["gate_decision"] == GateDecision.EXECUTE


async def test_capability_check_blocked_when_no_envelope():
    gate = MagicMock(spec=CapabilityGate)
    cfg = make_config(capability_gate=gate)
    result = await capability_check(base_state(envelope=None), cfg)
    assert result["gate_decision"] == GateDecision.BLOCKED


async def test_capability_check_passes_session_overrides():
    gate = MagicMock(spec=CapabilityGate)
    gate.evaluate.return_value = GateDecision.EXECUTE
    cfg = make_config(capability_gate=gate)
    overrides = {"research.read": "autonomous"}
    await capability_check(base_state(session_overrides=overrides), cfg)
    gate.evaluate.assert_called_once_with(
        agent="research", intent="read", session_overrides=overrides
    )


# ── execution.execute_tool ────────────────────────────────────────────────────


async def test_execute_tool_single_agent(monkeypatch):
    mock_result = AgentResult(agent="research", response="found it")
    mock_agent = AsyncMock()
    mock_agent.run = AsyncMock(return_value=mock_result)

    import ze_agents.registry as reg

    monkeypatch.setitem(reg._instances, "research", mock_agent)

    ctx = AgentContext(
        session_id="s1", prompt="test", intent="read", memory=MemoryContext()
    )
    state = base_state(agent_context=ctx, gate_decision=GateDecision.EXECUTE)
    result = await execution.execute_tool(state, make_config())
    assert result["agent_result"].response == "found it"
    assert result["subtask_results"] == []


async def test_execute_tool_compound_accumulates_results(monkeypatch):
    research_result = AgentResult(agent="research", response="research data")
    companion_result = AgentResult(agent="companion", response="companion data")

    mock_research = AsyncMock()
    mock_research.run = AsyncMock(return_value=research_result)
    mock_companion = AsyncMock()
    mock_companion.run = AsyncMock(return_value=companion_result)

    import ze_agents.registry as reg

    monkeypatch.setitem(reg._instances, "research", mock_research)
    monkeypatch.setitem(reg._instances, "companion", mock_companion)

    subtasks = [
        SubTask(agent="research", intent="read", prompt="search part"),
        SubTask(agent="companion", intent="reason", prompt="reason part"),
    ]
    envelope = make_envelope(is_compound=True, subtasks=subtasks)
    ctx = AgentContext(
        session_id="s1", prompt="compound", intent="read", memory=MemoryContext()
    )
    state = base_state(envelope=envelope, agent_context=ctx)

    result = await execution.execute_tool(state, make_config())
    assert result["agent_result"] is None
    assert len(result["subtask_results"]) == 2


async def test_execute_tool_raises_timeout(monkeypatch):
    async def slow_run(ctx):
        await asyncio.sleep(999)

    mock_agent = MagicMock()
    mock_agent.run = slow_run
    type(mock_agent).timeout = 0.01  # ze-core reads timeout from type(instance)

    import ze_agents.registry as reg

    monkeypatch.setitem(reg._instances, "research", mock_agent)

    ctx = AgentContext(
        session_id="s1", prompt="test", intent="read", memory=MemoryContext()
    )
    state = base_state(agent_context=ctx)
    with pytest.raises(AgentTimeoutError):
        await execution.execute_tool(state, make_config())


# ── confirmation.await_confirmation ──────────────────────────────────────────


async def test_await_confirmation_clears_pending_and_sets_execute():
    from ze_agents.types import GateDecision

    result = await await_confirmation(base_state(), make_config())
    assert result["pending_confirmation"] is False
    assert result["gate_decision"] == GateDecision.EXECUTE


# ── memory.write_memory ───────────────────────────────────────────────────────


async def test_write_memory_schedules_tasks_without_blocking():
    store = AsyncMock(spec=MemoryStore)
    store.write_episode = AsyncMock()
    store.propose_facts = AsyncMock()
    client = AsyncMock()
    client.complete = AsyncMock(return_value="[]")
    cfg = make_config(memory_store=store, openrouter_client=client)

    result_obj = AgentResult(agent="research", response="done")
    ctx = AgentContext(
        session_id="s1", prompt="hi", intent="read", memory=MemoryContext()
    )
    state = base_state(agent_context=ctx, agent_result=result_obj)

    result = await memory.write_memory(state, cfg)
    assert "messages" in result
    # Let background tasks run
    await asyncio.sleep(0)


async def test_write_memory_no_crash_if_no_agent_context():
    cfg = make_config()
    result = await memory.write_memory(base_state(agent_context=None), cfg)
    assert result == {}


# ── memory._write_contact_proposals ──────────────────────────────────────────


async def test_write_contact_proposals_writes_email_to_channel_store():
    from ze_sdk.channels import ChannelType
    from ze_personal.contacts.types import ContactProposal
    from ze_personal.graph.memory_hooks import _write_contact_proposals

    person_store = AsyncMock()
    person_store.get_by_name = AsyncMock(return_value=[])
    stored_person = MagicMock()
    stored_person.id = "person-uuid-1"
    person_store.upsert = AsyncMock(return_value=stored_person)
    person_store.add_source = AsyncMock()

    channel_store = AsyncMock()
    channel_store.upsert = AsyncMock()

    proposals = [
        ContactProposal(
            name="Alice",
            classification="professional",
            relationship="email contact",
            contact_info={"email": "alice@example.com"},
            confidence=0.7,
            confirmed=False,
        )
    ]

    await _write_contact_proposals(
        person_store,
        proposals,
        "test prompt",
        contact_channel_store=channel_store,
    )

    channel_store.upsert.assert_awaited_once()
    call_args = channel_store.upsert.call_args
    handle = call_args.args[1]
    assert handle.channel_type == ChannelType.EMAIL
    assert handle.handle == "alice@example.com"


async def test_write_contact_proposals_skips_channel_write_when_no_email():
    from ze_personal.contacts.types import ContactProposal
    from ze_personal.graph.memory_hooks import _write_contact_proposals

    person_store = AsyncMock()
    person_store.get_by_name = AsyncMock(return_value=[])
    stored_person = MagicMock()
    stored_person.id = "person-uuid-1"
    person_store.upsert = AsyncMock(return_value=stored_person)
    person_store.add_source = AsyncMock()

    channel_store = AsyncMock()
    channel_store.upsert = AsyncMock()

    proposals = [
        ContactProposal(name="Bob", contact_info={}, confidence=0.7, confirmed=False)
    ]

    await _write_contact_proposals(
        person_store,
        proposals,
        "test prompt",
        contact_channel_store=channel_store,
    )

    channel_store.upsert.assert_not_awaited()


async def test_write_contact_proposals_works_without_channel_store():
    from ze_personal.contacts.types import ContactProposal
    from ze_personal.graph.memory_hooks import _write_contact_proposals

    person_store = AsyncMock()
    person_store.get_by_name = AsyncMock(return_value=[])
    stored_person = MagicMock()
    stored_person.id = "person-uuid-1"
    person_store.upsert = AsyncMock(return_value=stored_person)
    person_store.add_source = AsyncMock()

    proposals = [
        ContactProposal(
            name="Carol", contact_info={"email": "carol@x.com"}, confidence=0.8
        )
    ]
    await _write_contact_proposals(person_store, proposals, "prompt")


async def test_write_contact_proposals_writes_channel_for_existing_contact():
    from ze_sdk.channels import ChannelType
    from ze_personal.contacts.types import ContactProposal, Person
    from ze_personal.graph.memory_hooks import _write_contact_proposals
    from datetime import datetime, timezone

    existing = Person(
        name="Alice",
        id="existing-uuid",
        confirmed=True,
        first_seen=datetime.now(timezone.utc),
        last_mentioned=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    person_store = AsyncMock()
    person_store.get_by_name = AsyncMock(return_value=[existing])
    person_store.add_source = AsyncMock()

    channel_store = AsyncMock()
    channel_store.upsert = AsyncMock()

    proposals = [
        ContactProposal(
            name="Alice", contact_info={"email": "alice@example.com"}, confidence=0.7
        )
    ]
    await _write_contact_proposals(
        person_store,
        proposals,
        "prompt",
        contact_channel_store=channel_store,
    )

    channel_store.upsert.assert_awaited_once()
    handle = channel_store.upsert.call_args.args[1]
    assert handle.channel_type == ChannelType.EMAIL
    assert handle.handle == "alice@example.com"


# ── memory.synthesize ─────────────────────────────────────────────────────────


async def test_synthesize_merges_subtask_results():
    client = AsyncMock()
    client.complete = AsyncMock(return_value="synthesized response")
    cfg = make_config(openrouter_client=client)

    subtask_results = [
        AgentResult(agent="research", response="research part"),
        AgentResult(agent="companion", response="companion part"),
    ]
    state = base_state(subtask_results=subtask_results)
    result = await synthesize(state, cfg)
    assert result["final_response"] == "synthesized response"
    client.complete.assert_awaited_once()


async def test_synthesize_returns_empty_when_no_subtasks():
    cfg = make_config()
    result = await synthesize(base_state(subtask_results=[]), cfg)
    assert result == {}


# ── routing.plan_sequential ───────────────────────────────────────────────────


async def test_plan_sequential_identifies_high_risk_steps():
    from ze_automation.workflow.planner import WorkflowPlanner
    from ze_automation.workflow.types import WorkflowStep

    steps = [
        WorkflowStep(task="Research AI news", agent_hint="research", intent="read"),
        WorkflowStep(task="Draft email summary", agent_hint="email", intent="create"),
        WorkflowStep(task="Schedule meeting", agent_hint="calendar", intent="create"),
    ]
    planner = AsyncMock(spec=WorkflowPlanner)
    planner.plan = AsyncMock(return_value=steps)

    gate = MagicMock(spec=CapabilityGate)
    gate.evaluate = MagicMock(
        side_effect=[
            GateDecision.EXECUTE,  # research.read — autonomous
            GateDecision.DRAFT,  # email.create — high-risk
            GateDecision.AWAIT_CONFIRMATION,  # calendar.create — high-risk
        ]
    )

    cfg = make_config(capability_gate=gate)
    cfg["configurable"]["workflow_planner"] = planner

    state = base_state(prompt="Research AI news, draft email, schedule meeting")
    result = await routing.plan_sequential(state, cfg)

    assert result["dynamic_plan_steps"] == steps
    assert result["dynamic_plan_high_risk"] == [1, 2]
    planner.plan.assert_awaited_once_with(
        "Research AI news, draft email, schedule meeting"
    )


async def test_plan_sequential_empty_high_risk_when_all_autonomous():
    from ze_automation.workflow.planner import WorkflowPlanner
    from ze_automation.workflow.types import WorkflowStep

    steps = [
        WorkflowStep(task="Look up AI news", agent_hint="research", intent="read"),
        WorkflowStep(task="Look up stock prices", agent_hint="research", intent="read"),
    ]
    planner = AsyncMock(spec=WorkflowPlanner)
    planner.plan = AsyncMock(return_value=steps)

    gate = MagicMock(spec=CapabilityGate)
    gate.evaluate = MagicMock(return_value=GateDecision.EXECUTE)

    cfg = make_config(capability_gate=gate)
    cfg["configurable"]["workflow_planner"] = planner

    state = base_state(prompt="Look up AI news and stock prices")
    result = await routing.plan_sequential(state, cfg)

    assert result["dynamic_plan_steps"] == steps
    assert result["dynamic_plan_high_risk"] == []


async def test_plan_sequential_returns_error_on_plan_failure():
    from ze_agents.errors import WorkflowPlanError
    from ze_automation.workflow.planner import WorkflowPlanner

    planner = AsyncMock(spec=WorkflowPlanner)
    planner.plan = AsyncMock(side_effect=WorkflowPlanError("malformed plan"))

    cfg = make_config()
    cfg["configurable"]["workflow_planner"] = planner

    state = base_state(prompt="do something complex")
    result = await routing.plan_sequential(state, cfg)

    assert "couldn't plan" in result["final_response"]
    assert result["dynamic_plan_steps"] is None
    assert result["dynamic_plan_high_risk"] == []


async def test_plan_sequential_uses_agent_hint_for_gate_check():
    from ze_automation.workflow.planner import WorkflowPlanner
    from ze_automation.workflow.types import WorkflowStep

    steps = [WorkflowStep(task="Do something", agent_hint=None, intent="execute")]
    planner = AsyncMock(spec=WorkflowPlanner)
    planner.plan = AsyncMock(return_value=steps)

    gate = MagicMock(spec=CapabilityGate)
    gate.evaluate = MagicMock(return_value=GateDecision.EXECUTE)

    cfg = make_config(capability_gate=gate)
    cfg["configurable"]["workflow_planner"] = planner

    state = base_state(prompt="do something")
    await routing.plan_sequential(state, cfg)

    # Falls back to "research" when agent_hint is None
    gate.evaluate.assert_called_once_with("research", "execute", {})
