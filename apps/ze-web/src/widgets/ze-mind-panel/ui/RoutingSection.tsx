import type { WsTraceUpdateFrame } from "@ze/client";
import { RoutingBadge } from "@/widgets/message-trace/ui/RoutingBadge";
import { TraceSection } from "@/widgets/message-trace/ui/TraceSection";

interface RoutingSectionProps {
  trace: WsTraceUpdateFrame;
}

export function RoutingSection({ trace }: RoutingSectionProps) {
  return (
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
  );
}
