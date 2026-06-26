import type { WsTraceUpdateFrame } from "@ze/client";
import { MemoryChunkList } from "@/widgets/message-trace/ui/MemoryChunkList";
import { TraceSection } from "@/widgets/message-trace/ui/TraceSection";

interface MemorySectionProps {
  chunks: WsTraceUpdateFrame["memory_chunks"];
}

export function MemorySection({ chunks }: MemorySectionProps) {
  return (
    <TraceSection title="Memory" count={chunks.length}>
      <MemoryChunkList chunks={chunks} />
    </TraceSection>
  );
}
