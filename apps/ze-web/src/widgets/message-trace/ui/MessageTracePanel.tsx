import { useMessageTraceQuery } from "@/entities/message";
import { MemoryChunkList } from "./MemoryChunkList";
import { RoutingBadge } from "./RoutingBadge";
import { ToolCallList } from "./ToolCallList";
import { TraceSection } from "./TraceSection";

interface MessageTracePanelProps {
  messageId: string;
}

export function MessageTracePanel({ messageId }: MessageTracePanelProps) {
  const { data: trace, isLoading } = useMessageTraceQuery(messageId, true);

  if (isLoading) {
    return (
      <div className="mt-1 rounded-xl border border-white/[0.06] bg-white/[0.03] px-3 py-2 text-xs text-smoke">
        Loading trace…
      </div>
    );
  }

  if (!trace) {
    return (
      <div className="mt-1 rounded-xl border border-white/[0.06] bg-white/[0.03] px-3 py-2 text-xs text-smoke/80 italic">
        No trace available for this message.
      </div>
    );
  }

  return (
    <div className="mt-1 rounded-xl border border-white/[0.06] bg-white/[0.03] overflow-hidden text-xs">
      <TraceSection title="Routing">
        <RoutingBadge
          agent={trace.agent}
          routingMethod={trace.routing_method}
          confidence={trace.confidence}
          scoreGap={trace.score_gap}
          isCompound={trace.is_compound}
          subtasks={trace.subtasks}
          totalDurationMs={trace.total_duration_ms}
        />
      </TraceSection>

      <TraceSection title="Memory retrieved" count={trace.memory_chunks.length}>
        <MemoryChunkList chunks={trace.memory_chunks} />
      </TraceSection>

      <TraceSection title="Tools called" count={trace.tool_calls.length}>
        <ToolCallList toolCalls={trace.tool_calls} />
      </TraceSection>
    </div>
  );
}
