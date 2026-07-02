import type { MessageTraceResponse, WsTraceUpdateFrame } from "@myguyze/ze-client";

export function toTraceFrame(
  messageId: string,
  trace: MessageTraceResponse,
): WsTraceUpdateFrame {
  return {
    type: "trace_update",
    message_id: messageId,
    agent: trace.agent,
    routing_method: trace.routing_method,
    confidence: trace.confidence,
    score_gap: trace.score_gap,
    is_compound: trace.is_compound,
    subtasks: trace.subtasks,
    memory_chunks: trace.memory_chunks,
    tool_calls: trace.tool_calls,
    total_duration_ms: trace.total_duration_ms,
  };
}
