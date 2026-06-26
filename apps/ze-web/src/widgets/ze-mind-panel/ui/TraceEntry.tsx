import type { WsTraceUpdateFrame } from "@ze/client";
import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { MemorySection } from "./MemorySection";
import { RoutingSection } from "./RoutingSection";
import { ToolsSection } from "./ToolsSection";

interface TraceEntryProps {
  trace: WsTraceUpdateFrame;
  index: number;
  defaultOpen?: boolean;
}

export function TraceEntry({ trace, index, defaultOpen = false }: TraceEntryProps) {
  const [open, setOpen] = useState(defaultOpen);
  const confidencePct = Math.round(trace.confidence * 100);

  return (
    <div className="border-b border-white/[0.06] last:border-b-0">
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
        <span className="px-1.5 py-0.5 rounded bg-plum-voltage/20 text-plum-voltage text-[10px] font-medium">
          {trace.agent}
        </span>
        {trace.total_duration_ms > 0 && (
          <span className="text-smoke/50 text-[10px] ml-auto">{trace.total_duration_ms}ms</span>
        )}
        {confidencePct > 0 && (
          <span className="text-smoke/50 text-[10px]">{confidencePct}%</span>
        )}
      </button>

      {open && (
        <div className="pb-1">
          <RoutingSection trace={trace} />
          <MemorySection chunks={trace.memory_chunks} />
          <ToolsSection toolCalls={trace.tool_calls} />
        </div>
      )}
    </div>
  );
}
