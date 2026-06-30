import type { WsTraceUpdateFrame } from "@myguyze/ze-client";
import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { MemorySection } from "./MemorySection";
import { RoutingSection } from "./RoutingSection";
import { ToolsSection } from "./ToolsSection";

interface TraceEntryProps {
  trace: WsTraceUpdateFrame;
  index: number;
  defaultOpen?: boolean;
  live?: boolean;
}

export function TraceEntry({ trace, index, defaultOpen = false, live }: TraceEntryProps) {
  const [open, setOpen] = useState(defaultOpen);
  const confidencePct = Math.round(trace.confidence * 100);

  return (
    <div className={`border-b border-white/[0.06] last:border-b-0${live ? " ring-1 ring-inset ring-plum-voltage/20" : ""}`}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 w-full px-3 py-2 text-left hover:bg-white/[0.03] transition-colors"
      >
        {open ? (
          <ChevronDown className="w-3 h-3 flex-shrink-0 text-smoke" />
        ) : (
          <ChevronRight className="w-3 h-3 flex-shrink-0 text-smoke" />
        )}
        <span className="text-smoke text-[10px] font-mono">#{index + 1}</span>
        {trace.agent ? (
          <span className="px-1.5 py-0.5 rounded bg-plum-voltage/20 text-plum-voltage text-[10px] font-medium">
            {trace.agent}
          </span>
        ) : live ? (
          <span className="w-16 h-3.5 rounded bg-white/[0.06] animate-pulse" />
        ) : null}
        {trace.total_duration_ms > 0 && (
          <span className="text-smoke/50 text-[10px] ml-auto">{trace.total_duration_ms}ms</span>
        )}
        {confidencePct > 0 && (
          <span className="text-smoke/50 text-[10px]">{confidencePct}%</span>
        )}
      </button>

      {open && (
        <div className="pb-1">
          <RoutingSection trace={trace} live={live} />
          <MemorySection chunks={trace.memory_chunks} live={live} />
          <ToolsSection toolCalls={trace.tool_calls} live={live} />
        </div>
      )}
    </div>
  );
}
