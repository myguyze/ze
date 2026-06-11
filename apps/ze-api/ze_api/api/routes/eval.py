from fastapi import APIRouter, Header, HTTPException, Request, status
from ze_core.telemetry.context import set_flow_context

from ze_api.api.schemas import EvalChatRequest, EvalChatResponse, EvalRoutingInfo, EvalToolCall
from ze_api.logging import get_logger

log = get_logger(__name__)

router = APIRouter(tags=["eval"])


def _check_api_key(x_ze_api_key: str | None, settings) -> None:
    if not x_ze_api_key or x_ze_api_key != settings.ze_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


@router.post(
    "/eval/chat",
    response_model=EvalChatResponse,
    summary="Eval chat",
    description=(
        "Send a prompt directly to the Ze graph and receive a structured response "
        "with routing metadata. Intended for automated evaluation and LLM-as-tester workflows."
    ),
)
async def eval_chat(
    body: EvalChatRequest,
    request: Request,
    x_ze_api_key: str | None = Header(default=None),
) -> EvalChatResponse:
    _check_api_key(x_ze_api_key, request.app.state.settings)

    # Set telemetry context so llm_cost_log captures this eval session.
    # bot.invoke() prepends "eval-", so the stored session_id = f"eval-{body.session_id}".
    set_flow_context("eval", session_id=body.session_id)

    ze_bot = request.app.state.ze_bot
    try:
        final_state = await ze_bot.invoke(body.prompt, body.session_id)
    except Exception as exc:
        log.exception("eval_graph_error", session_id=body.session_id, error=str(exc))
        return EvalChatResponse(
            session_id=body.session_id,
            response=None,
            agent_used=None,
            routing=None,
            pending_confirmation=False,
            error=str(exc),
        )

    envelope = final_state.get("envelope")
    routing = None
    if envelope is not None:
        routing = EvalRoutingInfo(
            primary_agent=envelope.primary_agent,
            confidence=envelope.confidence,
            routing_method=envelope.routing_method,
            is_compound=envelope.is_compound,
            score_gap=envelope.score_gap,
            raw_scores=envelope.raw_scores or {},
        )

    agent_result = final_state.get("agent_result")
    response_text = final_state.get("final_response")
    if response_text is None and agent_result is not None:
        response_text = agent_result.response

    tool_calls: list[EvalToolCall] = []
    tokens_used = 0
    memory_proposals_count = 0
    if agent_result is not None:
        tool_calls = [
            EvalToolCall(
                tool_name=tc.tool_name,
                args=tc.args,
                duration_ms=tc.duration_ms,
                success=tc.success,
                error=tc.error,
                is_draft=tc.is_draft,
            )
            for tc in (agent_result.tool_calls or [])
        ]
        tokens_used = agent_result.tokens_used or 0
        memory_proposals_count = len(agent_result.memory_proposals or [])

    return EvalChatResponse(
        session_id=body.session_id,
        response=response_text,
        agent_used=envelope.primary_agent if envelope else None,
        routing=routing,
        pending_confirmation=bool(final_state.get("pending_confirmation")),
        error=final_state.get("error"),
        tool_calls=tool_calls,
        tokens_used=tokens_used,
        memory_proposals_count=memory_proposals_count,
    )
