import type { WorkflowExecutionResponse } from "@myguyze/ze-client";
import { CheckCircle2, XCircle, Clock, ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";

function formatDuration(startedAt: string | null, completedAt: string | null): string {
  if (!startedAt || !completedAt) return "";
  const ms = new Date(completedAt).getTime() - new Date(startedAt).getTime();
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function ExecutionRow({ execution }: { execution: WorkflowExecutionResponse }) {
  const [expanded, setExpanded] = useState(false);
  const succeeded = execution.status === "completed";
  const duration = formatDuration(execution.started_at, execution.completed_at);

  return (
    <div className="border border-white/10 rounded-pill overflow-hidden">
      <button
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-white/[0.03] transition-colors"
        onClick={() => setExpanded((v) => !v)}
      >
        {succeeded ? (
          <CheckCircle2 className="w-4 h-4 text-green-400 flex-shrink-0" />
        ) : (
          <XCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
        )}
        <div className="flex-1 min-w-0">
          <span className="text-sm text-white capitalize">{execution.status}</span>
          {execution.started_at && (
            <span className="ml-2 text-xs text-smoke">{formatTimestamp(execution.started_at)}</span>
          )}
        </div>
        {duration && (
          <span className="flex items-center gap-1 text-xs text-smoke flex-shrink-0">
            <Clock className="w-3 h-3" />
            {duration}
          </span>
        )}
        {(execution.step_results.length > 0 || !!execution.summary) && (
          expanded
            ? <ChevronDown className="w-3.5 h-3.5 text-smoke flex-shrink-0" />
            : <ChevronRight className="w-3.5 h-3.5 text-smoke flex-shrink-0" />
        )}
      </button>

      {expanded && (
        <div className="border-t border-white/10 px-4 py-3 space-y-3">
          {execution.summary && (
            <div className="pb-3 border-b border-white/10">
              <p className="text-xs text-smoke/70 uppercase tracking-wide mb-1">Summary</p>
              <p className="text-xs text-white/80 whitespace-pre-wrap">{execution.summary}</p>
            </div>
          )}
          {execution.step_results.map((result) => (
            <div key={result.step_index} className="flex gap-3">
              <div className="flex-shrink-0 mt-0.5">
                {result.success
                  ? <CheckCircle2 className="w-3.5 h-3.5 text-green-400" />
                  : <XCircle className="w-3.5 h-3.5 text-red-400" />
                }
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs text-white/70">{result.task}</p>
                {result.output && (
                  <p className="mt-0.5 text-xs text-smoke whitespace-pre-wrap">{result.output}</p>
                )}
                {result.error && (
                  <p className="mt-0.5 text-xs text-red-400">{result.error}</p>
                )}
                <p className="mt-0.5 text-xs text-smoke/60">{result.duration_ms}ms</p>
              </div>
            </div>
          ))}
          {execution.error && !execution.summary && (
            <p className="text-xs text-red-400 pt-1 border-t border-white/10">{execution.error}</p>
          )}
        </div>
      )}
    </div>
  );
}

interface Props {
  executions: WorkflowExecutionResponse[];
}

export function WorkflowExecutionsList({ executions }: Props) {
  if (!executions.length) {
    return <p className="text-sm text-smoke">No runs yet.</p>;
  }

  return (
    <div className="space-y-2">
      {executions.map((ex) => (
        <ExecutionRow key={ex.id} execution={ex} />
      ))}
    </div>
  );
}
