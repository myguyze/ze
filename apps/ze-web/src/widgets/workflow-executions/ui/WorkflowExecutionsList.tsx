import type { WorkflowExecutionResponse } from "@myguyze/ze-client";
import { CheckCircle2, XCircle, Clock, Loader2, MessageCircle } from "lucide-react";
import { useOverlayStore } from "@/features/open-context-overlay";

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

function buildChatBrief(workflowName: string, execution: WorkflowExecutionResponse): string {
  const date = execution.started_at ? formatTimestamp(execution.started_at) : "unknown date";
  const duration = formatDuration(execution.started_at, execution.completed_at);
  const stepCount = execution.step_results.length;
  const status = execution.status === "completed" ? "completed" : "failed";
  const durationPart = duration ? ` in ${duration}` : "";
  const errorPart = execution.error ? `. Error: ${execution.error}` : "";
  return `Tell me about the "${workflowName}" workflow run from ${date}. It ${status}${durationPart} with ${stepCount} step${stepCount !== 1 ? "s" : ""}${errorPart}.`;
}

interface ExecutionRowProps {
  execution: WorkflowExecutionResponse;
  selected: boolean;
  onClick: () => void;
  onChat: () => void;
}

function ExecutionRow({ execution, selected, onClick, onChat }: ExecutionRowProps) {
  const isRunning = execution.status === "running";
  const succeeded = execution.status === "completed";
  const duration = formatDuration(execution.started_at, execution.completed_at);
  const stepCount = execution.step_results.length;

  return (
    <div className="group relative">
      <button
        className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl text-left transition-colors ${
          selected
            ? "bg-white/[0.07] border border-white/20"
            : "border border-white/10 hover:bg-white/[0.04] hover:border-white/15"
        }`}
        onClick={onClick}
      >
        <div className="flex-shrink-0">
          {isRunning ? (
            <Loader2 className="w-4 h-4 text-plum-voltage animate-spin" />
          ) : succeeded ? (
            <CheckCircle2 className="w-4 h-4 text-green-400" />
          ) : (
            <XCircle className="w-4 h-4 text-red-400" />
          )}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs text-white/80 capitalize">{isRunning ? "Running…" : execution.status}</span>
            {duration && (
              <span className="flex items-center gap-0.5 text-xs text-smoke flex-shrink-0">
                <Clock className="w-3 h-3" />
                {duration}
              </span>
            )}
          </div>
          <div className="flex items-center justify-between mt-0.5">
            {execution.started_at && (
              <span className="text-xs text-smoke/70">{formatTimestamp(execution.started_at)}</span>
            )}
            {!isRunning && (
              <span className="text-xs text-smoke/50">{stepCount} step{stepCount !== 1 ? "s" : ""}</span>
            )}
          </div>
        </div>
      </button>

      {!isRunning && (
        <button
          className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-lg text-smoke/40 hover:text-plum-voltage hover:bg-plum-voltage/10 transition-all opacity-0 group-hover:opacity-100"
          title="Chat about this run"
          onClick={(e) => {
            e.stopPropagation();
            onClick();
            onChat();
          }}
        >
          <MessageCircle className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
}

interface Props {
  workflowName: string;
  executions: WorkflowExecutionResponse[];
  selectedId?: string | null;
  onSelect: (execution: WorkflowExecutionResponse) => void;
}

export function WorkflowExecutionsList({ workflowName, executions, selectedId, onSelect }: Props) {
  const openForExecution = useOverlayStore((s) => s.openForExecution);

  if (!executions.length) {
    return <p className="text-sm text-smoke">No runs yet.</p>;
  }

  function handleChat(execution: WorkflowExecutionResponse) {
    openForExecution({
      screen: "workflow run",
      entityId: execution.id,
      prefillMessage: buildChatBrief(workflowName, execution),
    });
  }

  return (
    <div className="space-y-2">
      {executions.map((ex) => (
        <ExecutionRow
          key={ex.id}
          execution={ex}
          selected={ex.id === selectedId}
          onClick={() => onSelect(ex)}
          onChat={() => handleChat(ex)}
        />
      ))}
    </div>
  );
}
