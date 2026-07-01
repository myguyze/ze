import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Workflow } from "lucide-react";
import {
  useWorkflowDetailQuery,
  useWorkflowExecutionsQuery,
  useLiveExecutionQuery,
  useTriggerWorkflowMutation,
  formatSchedule,
} from "@/entities/workflow";
import { WorkflowStepsList } from "@/widgets/workflow-steps";
import { WorkflowExecutionsList, LiveRunPanel } from "@/widgets/workflow-executions";
import { ListSkeleton, ErrorState, Button } from "@/shared/ui";

export function WorkflowDetailPage() {
  const { workflowId } = useParams<{ workflowId: string }>();
  const navigate = useNavigate();
  const [liveExecutionId, setLiveExecutionId] = useState<string | null>(null);

  const { data: detail, isLoading, isError, refetch } = useWorkflowDetailQuery(workflowId ?? "");
  const { data: executions, isLoading: execLoading } = useWorkflowExecutionsQuery(workflowId ?? "");
  const { data: liveExecution } = useLiveExecutionQuery(workflowId ?? "", liveExecutionId);

  const trigger = useTriggerWorkflowMutation();

  function handleTrigger() {
    if (!workflowId) return;
    trigger.mutate(workflowId, {
      onSuccess: (data) => {
        setLiveExecutionId(data.execution_id);
      },
    });
  }

  // Clear live panel once the run is done and history has refreshed
  const liveRunFinished = liveExecution && liveExecution.status !== "running";

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
              disabled={trigger.isPending || liveExecution?.status === "running"}
              onClick={handleTrigger}
            >
              {trigger.isPending ? "Starting…" : "Run now"}
            </Button>
          )}
        </div>
      </div>

      {/* Live run panel — shown while a triggered run is in progress or just finished */}
      {liveExecution && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-medium text-white/70 uppercase tracking-wide">
              Live Run
            </h2>
            {liveRunFinished && (
              <button
                className="text-xs text-smoke hover:text-white transition-colors"
                onClick={() => setLiveExecutionId(null)}
              >
                Dismiss
              </button>
            )}
          </div>
          <LiveRunPanel execution={liveExecution} workflow={detail} />
        </div>
      )}

      {/* Main layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Steps — 2/3 width on large screens */}
        <div className="lg:col-span-2">
          <h2 className="text-sm font-medium text-white/70 uppercase tracking-wide mb-3">
            Steps
          </h2>
          <WorkflowStepsList steps={detail.steps} />
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
