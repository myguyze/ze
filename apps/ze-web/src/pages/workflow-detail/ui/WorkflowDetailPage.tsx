import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Workflow, Loader2, CheckCircle2, XCircle } from "lucide-react";
import ReactMarkdown from "react-markdown";
import type { WorkflowExecutionResponse } from "@myguyze/ze-client";
import {
  useWorkflowDetailQuery,
  useWorkflowExecutionsQuery,
  useLiveExecutionQuery,
  useTriggerWorkflowMutation,
  formatSchedule,
  averageSuccessfulRunDuration,
} from "@/entities/workflow";
import { WorkflowStepsList } from "@/widgets/workflow-steps";
import { WorkflowExecutionsList } from "@/widgets/workflow-executions";
import { ListSkeleton, ErrorState, Button, PageShell, SectionPanel } from "@/shared/ui";

export function WorkflowDetailPage() {
  const { workflowId } = useParams<{ workflowId: string }>();
  const navigate = useNavigate();
  const [liveExecutionId, setLiveExecutionId] = useState<string | null>(null);
  const [selectedExecution, setSelectedExecution] = useState<WorkflowExecutionResponse | null>(null);

  const { data: detail, isLoading, isError, refetch } = useWorkflowDetailQuery(workflowId ?? "");
  const { data: executions, isLoading: execLoading } = useWorkflowExecutionsQuery(workflowId ?? "");
  const { data: liveExecution } = useLiveExecutionQuery(workflowId ?? "", liveExecutionId);

  const trigger = useTriggerWorkflowMutation();

  const isRunning = trigger.isPending || liveExecution?.status === "running";

  const avgRunDuration = executions ? averageSuccessfulRunDuration(executions) : null;

  const displayExecution: WorkflowExecutionResponse | null | undefined =
    isRunning ? liveExecution : (selectedExecution ?? liveExecution);

  const displayedId = displayExecution?.id ?? null;

  function handleTrigger() {
    if (!workflowId) return;
    setSelectedExecution(null);
    trigger.mutate(workflowId, {
      onSuccess: (data) => {
        setLiveExecutionId(data.execution_id);
      },
    });
  }

  function handleSelectExecution(ex: WorkflowExecutionResponse) {
    setSelectedExecution(ex);
  }

  if (isLoading) {
    return (
      <PageShell className="max-w-5xl mx-auto">
        <ListSkeleton count={4} />
      </PageShell>
    );
  }

  if (isError || !detail) {
    return (
      <PageShell className="max-w-5xl mx-auto">
        <ErrorState message="Could not load workflow." onRetry={() => void refetch()} />
      </PageShell>
    );
  }

  return (
    <PageShell className="max-w-5xl mx-auto">
      {/* Header */}
      <div>
        <button
          className="flex items-center gap-1.5 text-xs text-smoke hover:text-white transition-colors mb-6"
          onClick={() => navigate("/workflows")}
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Workflows
        </button>

        <div className="flex items-start justify-between gap-6">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-xl bg-plum-voltage/10 border border-plum-voltage/20 flex items-center justify-center flex-shrink-0 mt-0.5">
              <Workflow className="w-5 h-5 text-plum-voltage" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-white leading-tight">{detail.name}</h1>
              {detail.description && (
                <p className="text-sm text-smoke/80 mt-2 leading-relaxed max-w-2xl">{detail.description}</p>
              )}
              <div className="flex flex-wrap items-center gap-2 mt-4">
                <span
                  className={
                    detail.enabled
                      ? "inline-block px-2.5 py-0.5 rounded-full border border-plum-voltage/50 text-plum-voltage text-xs"
                      : "inline-block px-2.5 py-0.5 rounded-full border border-white/20 text-smoke text-xs"
                  }
                >
                  {detail.enabled ? "active" : "paused"}
                </span>
                <span className="inline-block px-2.5 py-0.5 rounded-full border border-white/15 text-smoke text-xs">
                  {formatSchedule(detail.schedule)}
                </span>
                {avgRunDuration && (
                  <span className="inline-block px-2.5 py-0.5 rounded-full border border-white/15 text-smoke text-xs">
                    {avgRunDuration} avg run
                  </span>
                )}
              </div>
            </div>
          </div>

          {detail.enabled && (
            <Button
              size="sm"
              variant="outline"
              disabled={isRunning}
              onClick={handleTrigger}
            >
              {trigger.isPending ? "Starting…" : "Run now"}
            </Button>
          )}
        </div>
      </div>

      {/* Main layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Steps — 2/3 width */}
        <SectionPanel className="lg:col-span-2">
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-xs font-semibold text-white/40 uppercase tracking-widest">Steps</h2>
            <StepsStatus
              liveExecution={liveExecution}
              displayExecution={displayExecution}
              isRunning={isRunning}
              onClear={() => {
                setLiveExecutionId(null);
                setSelectedExecution(null);
              }}
            />
          </div>

          <WorkflowStepsList steps={detail.steps} execution={displayExecution} />

          {displayExecution?.summary && displayExecution.status !== "running" && (
            <div className="mt-5 pt-5 border-t border-white/[0.06]">
              <p className="text-xs font-semibold text-white/40 uppercase tracking-widest mb-3">Summary</p>
              <div className="text-sm text-white/80 leading-relaxed space-y-1.5">
                <ReactMarkdown
                  components={{
                    h1: ({ children }) => <p className="font-semibold text-white mt-3 mb-1 text-base">{children}</p>,
                    h2: ({ children }) => <p className="font-semibold text-white/90 mt-3 mb-1">{children}</p>,
                    h3: ({ children }) => <p className="font-medium text-white/80 mt-2 mb-0.5">{children}</p>,
                    p: ({ children }) => <p className="mb-2">{children}</p>,
                    strong: ({ children }) => <strong className="text-white font-medium">{children}</strong>,
                    ul: ({ children }) => <ul className="list-disc pl-5 mb-2 space-y-0.5">{children}</ul>,
                    ol: ({ children }) => <ol className="list-decimal pl-5 mb-2 space-y-0.5">{children}</ol>,
                    li: ({ children }) => <li className="text-white/80">{children}</li>,
                    code: ({ children }) => <code className="bg-white/10 rounded px-1.5 py-0.5 text-xs font-mono">{children}</code>,
                    blockquote: ({ children }) => (
                      <blockquote className="border-l-2 border-white/20 pl-3 italic text-white/60 my-2">{children}</blockquote>
                    ),
                    hr: () => <hr className="border-white/10 my-3" />,
                  }}
                >
                  {displayExecution.summary}
                </ReactMarkdown>
              </div>
            </div>
          )}
        </SectionPanel>

        {/* Run history sidebar */}
        <SectionPanel>
          <h2 className="text-xs font-semibold text-white/40 uppercase tracking-widest mb-5">Run History</h2>
          {execLoading ? (
            <ListSkeleton count={3} />
          ) : (
            <WorkflowExecutionsList
              executions={executions ?? []}
              selectedId={displayedId}
              onSelect={handleSelectExecution}
            />
          )}
        </SectionPanel>
      </div>
    </PageShell>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

interface StepsStatusProps {
  liveExecution: WorkflowExecutionResponse | null | undefined;
  displayExecution: WorkflowExecutionResponse | null | undefined;
  isRunning: boolean;
  onClear: () => void;
}

function StepsStatus({ liveExecution, displayExecution, isRunning, onClear }: StepsStatusProps) {
  if (isRunning && liveExecution) {
    return (
      <div className="flex items-center gap-1.5">
        <Loader2 className="w-3.5 h-3.5 text-plum-voltage animate-spin" />
        <span className="text-xs text-plum-voltage">Running…</span>
      </div>
    );
  }

  if (liveExecution && displayExecution?.id === liveExecution.id) {
    if (liveExecution.status === "completed") {
      return (
        <div className="flex items-center gap-1.5">
          <CheckCircle2 className="w-3.5 h-3.5 text-green-400" />
          <span className="text-xs text-green-400">Complete</span>
          <button className="ml-1 text-xs text-smoke hover:text-white transition-colors" onClick={onClear}>
            Clear
          </button>
        </div>
      );
    }
    if (liveExecution.status === "failed") {
      return (
        <div className="flex items-center gap-1.5">
          <XCircle className="w-3.5 h-3.5 text-red-400" />
          <span className="text-xs text-red-400">Failed</span>
          <button className="ml-1 text-xs text-smoke hover:text-white transition-colors" onClick={onClear}>
            Clear
          </button>
        </div>
      );
    }
  }

  if (displayExecution && !liveExecution) {
    const succeeded = displayExecution.status === "completed";
    return (
      <div className="flex items-center gap-1.5">
        {succeeded
          ? <CheckCircle2 className="w-3.5 h-3.5 text-green-400" />
          : <XCircle className="w-3.5 h-3.5 text-red-400" />
        }
        <span className={`text-xs ${succeeded ? "text-green-400" : "text-red-400"}`}>
          {succeeded ? "Completed" : "Failed"}
        </span>
        <button className="ml-1 text-xs text-smoke hover:text-white transition-colors" onClick={onClear}>
          Clear
        </button>
      </div>
    );
  }

  return null;
}
