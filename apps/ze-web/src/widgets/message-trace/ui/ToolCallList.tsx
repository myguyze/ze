import type { ToolCallTraceResponse } from "@myguyze/ze-client";
import { CheckCircle, XCircle } from "lucide-react";

interface ToolCallListProps {
  toolCalls: ToolCallTraceResponse[];
}

export function ToolCallList({ toolCalls }: ToolCallListProps) {
  if (toolCalls.length === 0) {
    return <p className="text-xs text-smoke/60 italic">No tools called</p>;
  }

  return (
    <ul className="space-y-1.5">
      {toolCalls.map((tc, i) => (
        <li key={i} className="flex items-center gap-2 text-xs">
          {tc.success ? (
            <CheckCircle className="w-3 h-3 text-emerald-400 flex-shrink-0" />
          ) : (
            <XCircle className="w-3 h-3 text-red-400 flex-shrink-0" />
          )}
          <span className="font-mono text-white/90">{tc.name}</span>
          <span className="text-smoke">{tc.duration_ms}ms</span>
          {tc.result_snippet && (
            <span className="text-smoke/60 truncate max-w-[160px]">{tc.result_snippet}</span>
          )}
        </li>
      ))}
    </ul>
  );
}
