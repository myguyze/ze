import type { WsTraceUpdateFrame } from "@myguyze/ze-client";
import { MemoryChunkList } from "@/widgets/message-trace/ui/MemoryChunkList";
import { TraceSection } from "@/widgets/message-trace/ui/TraceSection";

interface MemorySectionProps {
  chunks: WsTraceUpdateFrame["memory_chunks"];
  live?: boolean;
}

export function MemorySection({ chunks, live }: MemorySectionProps) {
  return (
    <TraceSection title="Memory" count={chunks.length} loading={live && chunks.length === 0}>
      <MemoryChunkList chunks={chunks} />
    </TraceSection>
  );
}
