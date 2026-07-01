import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Workflow, Loader2, CheckCircle2, XCircle } from "lucide-react";
import {
  useWorkflowDetailQuery,
  useWorkflowExecutionsQuery,
  useLiveExecutionQuery,
  useTriggerWorkflowMutation,
  formatSchedule,
} from "@/entities/workflow";
import { WorkflowStepsList } from "@/widgets/workflow-steps";
import { WorkflowExecutionsList } from "@/widgets/workflow-executions";
import { ListSkeleton, ErrorState, Button } from "@/shared/ui";

export function WorkflowDetailPage() {
  const { workflowId } = useParams<{ workflowId: string }>();
  const navigate = useNavigate();
  const [liveExecutionId, setLiveExecutionId] = useState<string | null>(null);

  const { data: detail, isLoading, isError, refetch } = useWorkflowDetailQuery(workflowId ?? "");
  const { data: executions, isLoading: execLoading } = useWorkflowExecutionsQuery(workflowId ?? "");
  const { data: liveExecution } = useLiveExecutionQuery(workflowId ?? "", liveExecutionId);

  const trigger = useTriggerWorkflowMutation();

  const isRunning = trigger.isPending || liveExecution?.status === "running";

  function handleTrigger() {
    if (!workflowId) return;
    trigger.mutate(workflowId, {
      onSuccess: (data) => {
        setLiveExecutionId(data.execution_id);
      },
    });
  }

  if (isLoading) {
    return (
      <div className="px-4 py-8">
        <ListSkeleton count={4} />
      </div>
    );
  }

  if (isError || !detail) {
    return (
      <div className="px-4 py-8">
        <ErrorState message="Could not load workflow." onRetry={() => void refetch()} />
      </div>
    );
  }

  return (
    <div className="px-4 py-6 space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div>
        <button
          className="flex items-center gap-1.5 text-xs text-smoke hover:text-white transition-colors mb-4"
          onClick={() => navigate("/workflows")}
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Workflows
        </button>

        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <Workflow className="w-5 h-5 text-plum-voltage flex-shrink-0 mt-0.5" />
            <div>
              <h1 className="text-lg font-semibold text-white">{detail.name}</h1>
              {detail.description && (
                <p className="text-sm text-smoke mt-0.5">{detail.description}</p>
              )}
              <div className="flex flex-wrap items-center gap-2 mt-2">
                <span
                  className={
                    detail.enabled
                      ? "inline-block px-2 py-0.5 rounded-full border border-plum-voltage/50 text-plum-voltage text-xs"
                      : "inline-block px-2 py-0.5 rounded-full border border-white/20 text-smoke text-xs"
                  }
                >
                  {detail.enabled ? "active" : "paused"}
                </span>
                <span className="inline-block px-2 py-0.5 rounded-full border border-white/15 text-smoke text-xs">
                  {formatSchedule(detail.schedule)}
                </span>
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
        {/* Steps — 2/3 width on large screens */}
        <div className="lg:col-span-2 space-y-3">
          {/* Steps header with live run status */}
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-white/70 uppercase tracking-wide">
              Steps
            </h2>
            {liveExecution && (
              <div className="flex items-center gap-1.5">
                {liveExecution.status === "running" ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 text-plum-voltage animate-spin" />
                    <span className="text-xs text-plum-voltage">
                      Running — step {liveExecution.step_results.length + 1} / {detail.steps.length}
                    </span>
                  </>
                ) : liveExecution.status === "completed" ? (
                  <>
                    <CheckCircle2 className="w-3.5 h-3.5 text-green-400" />
                    <span className="text-xs text-green-400">Complete</span>
                    <button
                      className="ml-2 text-xs text-smoke hover:text-white transition-colors"
                      onClick={() => setLiveExecutionId(null)}
                    >
                      Clear
                    </button>
                  </>
                ) : (
                  <>
                    <XCircle className="w-3.5 h-3.5 text-red-400" />
                    <span className="text-xs text-red-400">Failed</span>
                    <button
                      className="ml-2 text-xs text-smoke hover:text-white transition-colors"
                      onClick={() => setLiveExecutionId(null)}
                    >
                      Clear
                    </button>
                  </>
                )}
              </div>
            )}
          </div>

          <WorkflowStepsList steps={detail.steps} execution={liveExecution} />

          {/* Summary footer — shown when run completes with a summary */}
          {liveExecution?.summary && liveExecution.status !== "running" && (
            <div className="mt-2 rounded-lg bg-white/[0.02] border border-white/10 px-4 py-3">
              <p className="text-xs text-smoke/70 uppercase tracking-wide mb-1.5">Summary</p>
              <p className="text-sm text-white/80 whitespace-pre-wrap leading-relaxed">
                {liveExecution.summary}
              </p>
            </div>
          )}
        </div>

        {/* Run history sidebar */}
        <div>
          <h2 className="text-sm font-medium text-white/70 uppercase tracking-wide mb-3">
            Run History
          </h2>
          {execLoading ? (
            <ListSkeleton count={3} />
          ) : (
            <WorkflowExecutionsList executions={executions ?? []} />
          )}
        </div>
      </div>
    </div>
  );
}
