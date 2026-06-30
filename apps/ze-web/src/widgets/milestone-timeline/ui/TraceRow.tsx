import type { ExecutionTraceResponse } from "@myguyze/ze-client";
import { CheckCircle, XCircle } from "lucide-react";

interface TraceRowProps {
  trace: ExecutionTraceResponse;
}

export function TraceRow({ trace }: TraceRowProps) {
  return (
    <div className="flex items-start gap-2 text-xs py-1.5 border-b border-white/5 last:border-0">
      {trace.success ? (
        <CheckCircle className="w-3 h-3 mt-0.5 text-emerald-400 flex-shrink-0" />
      ) : (
        <XCircle className="w-3 h-3 mt-0.5 text-red-400 flex-shrink-0" />
      )}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-mono text-white/90">{trace.tool_name}</span>
          <span className="text-smoke/60">{trace.duration_ms}ms</span>
          {!trace.success && trace.error && (
            <span className="text-red-400 truncate">{trace.error}</span>
          )}
        </div>
        {trace.result && (
          <p className="mt-0.5 text-smoke/60 truncate">{trace.result.slice(0, 200)}</p>
        )}
      </div>
    </div>
  );
}
