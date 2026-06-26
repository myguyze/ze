import type { WsTraceUpdateFrame } from "@ze/client";
import { ToolCallList } from "@/widgets/message-trace/ui/ToolCallList";
import { TraceSection } from "@/widgets/message-trace/ui/TraceSection";

interface ToolsSectionProps {
  toolCalls: WsTraceUpdateFrame["tool_calls"];
}

export function ToolsSection({ toolCalls }: ToolsSectionProps) {
  return (
    <TraceSection title="Tools" count={toolCalls.length}>
      <ToolCallList toolCalls={toolCalls} />
    </TraceSection>
  );
}
