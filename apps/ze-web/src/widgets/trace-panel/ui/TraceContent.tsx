import { Loader2 } from "lucide-react";
import { useEffect, useRef } from "react";
import type { WsTraceUpdateFrame } from "@myguyze/ze-client";
import { useSessionTraces, useTraceSocket, useTraceStore } from "@/features/trace-state";
import { TraceEmptyState } from "./TraceEmptyState";
import { TraceEntry } from "./TraceEntry";

const EMPTY_TRACE: Omit<WsTraceUpdateFrame, "type" | "message_id"> = {
  agent: "",
  routing_method: "",
  confidence: 0,
  score_gap: 0,
  is_compound: false,
  subtasks: [],
  memory_chunks: [],
  tool_calls: [],
  total_duration_ms: 0,
};

interface TraceContentProps {
  threadId: string;
  assistantMessageIds: string[];
}

export function TraceContent({ threadId, assistantMessageIds }: TraceContentProps) {
  useTraceSocket();
  const hydrating = useSessionTraces(threadId, assistantMessageIds);

  const traces = useTraceStore((s) => s.traces);
  const pending = useTraceStore((s) => s.pending);
  const pendingTrace = useTraceStore((s) => s.pendingTrace);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (traces.length > 0 || pendingTrace) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [traces.length, pendingTrace]);

  const liveTrace: WsTraceUpdateFrame | null = pendingTrace
    ? { type: "trace_update", message_id: "", ...EMPTY_TRACE, ...pendingTrace }
    : null;

  const showEmpty = traces.length === 0 && !pending && !liveTrace && !hydrating;

  return (
    <div className="text-xs h-full">
      {showEmpty ? (
        <TraceEmptyState />
      ) : (
        <div>
          {traces.map((trace, i) => (
            <TraceEntry
              key={trace.message_id}
              trace={trace}
              index={i}
              defaultOpen={i === traces.length - 1 && !liveTrace}
            />
          ))}
          {liveTrace && (
            <TraceEntry
              trace={liveTrace}
              index={traces.length}
              defaultOpen={true}
              live={true}
            />
          )}
          <div ref={bottomRef} />
        </div>
      )}

      {hydrating && traces.length === 0 && !liveTrace && (
        <div className="flex items-center justify-center gap-2 px-3 py-8 text-xs text-smoke">
          <Loader2 className="w-3 h-3 animate-spin flex-shrink-0" />
          Loading traces…
        </div>
      )}

      {pending && !liveTrace && (
        <div className="sticky bottom-0 flex items-center gap-2 px-3 py-2 bg-black/60 border-t border-white/[0.06] text-xs text-smoke">
          <Loader2 className="w-3 h-3 animate-spin flex-shrink-0" />
          Ze is thinking…
        </div>
      )}
    </div>
  );
}
