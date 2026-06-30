import type { WsTraceUpdateFrame } from "@ze/client";
import { ToolCallList } from "@/widgets/message-trace/ui/ToolCallList";
import { TraceSection } from "@/widgets/message-trace/ui/TraceSection";

interface ToolsSectionProps {
  toolCalls: WsTraceUpdateFrame["tool_calls"];
  live?: boolean;
}

export function ToolsSection({ toolCalls, live }: ToolsSectionProps) {
  return (
    <TraceSection title="Tools" count={toolCalls.length} loading={live && toolCalls.length === 0}>
      <ToolCallList toolCalls={toolCalls} />
    </TraceSection>
  );
}
