import type { WorkflowDetailResponse, WorkflowExecutionResponse } from "@myguyze/ze-client";
import { CheckCircle2, XCircle, Loader2, Circle } from "lucide-react";

type StepState = "completed-ok" | "completed-fail" | "running" | "failed-inferred" | "pending";

function resolveStepState(
  stepIndex: number,
  stepResults: WorkflowExecutionResponse["step_results"],
  executionStatus: string,
): StepState {
  const result = stepResults.find((r) => r.step_index === stepIndex);
  if (result) return result.success ? "completed-ok" : "completed-fail";

  const completedCount = stepResults.length;

  if (executionStatus === "running") {
    if (stepIndex === completedCount) return "running";
    return "pending";
  }

  // Execution ended but this step has no result — infer the failure point
  if (executionStatus === "failed" && stepIndex === completedCount) return "failed-inferred";
  return "pending";
}

interface Props {
  execution: WorkflowExecutionResponse;
  workflow: WorkflowDetailResponse;
}

export function LiveRunPanel({ execution, workflow }: Props) {
  const isRunning = execution.status === "running";
  const failed = execution.status === "failed";
  const completedCount = execution.step_results.length;

  return (
    <div className={`border rounded-pill overflow-hidden bg-white/[0.02] ${
      failed ? "border-destructive/30" : isRunning ? "border-plum-voltage/30" : "border-success/20"
    }`}>
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/10">
        {isRunning ? (
          <Loader2 className="w-4 h-4 text-plum-voltage animate-spin flex-shrink-0" />
        ) : failed ? (
          <XCircle className="w-4 h-4 text-destructive flex-shrink-0" />
        ) : (
          <CheckCircle2 className="w-4 h-4 text-success flex-shrink-0" />
        )}
        <span className="text-sm font-medium text-white">
          {isRunning ? "Running…" : failed ? "Run failed" : "Run complete"}
        </span>
        {isRunning && (
          <span className="ml-auto text-xs text-smoke">
            Step {completedCount + 1} / {workflow.steps.length}
          </span>
        )}
        {!isRunning && (
          <span className="ml-auto text-xs text-smoke">
            {completedCount} / {workflow.steps.length} steps
          </span>
        )}
      </div>

      {/* Step-by-step progress */}
      <div className="px-4 py-3 space-y-3">
        {workflow.steps.map((step, i) => {
          const state = resolveStepState(i, execution.step_results, execution.status);
          const result = execution.step_results.find((r) => r.step_index === i);

          return (
            <div key={i} className="flex gap-3">
              <div className="flex-shrink-0 mt-0.5">
                {state === "completed-ok" && <CheckCircle2 className="w-4 h-4 text-success" />}
                {state === "completed-fail" && <XCircle className="w-4 h-4 text-destructive" />}
                {state === "failed-inferred" && <XCircle className="w-4 h-4 text-destructive/60" />}
                {state === "running" && <Loader2 className="w-4 h-4 text-plum-voltage animate-spin" />}
                {state === "pending" && <Circle className="w-4 h-4 text-white/20" />}
              </div>
              <div className="flex-1 min-w-0">
                <p className={`text-sm ${
                  state === "pending" ? "text-white/30"
                  : state === "failed-inferred" ? "text-white/50"
                  : "text-white"
                }`}>
                  {step.task}
                </p>
                {result?.output && (
                  <p className="mt-1 text-xs text-smoke whitespace-pre-wrap line-clamp-3">
                    {result.output}
                  </p>
                )}
                {result?.error && (
                  <p className="mt-1 text-xs text-destructive">{result.error}</p>
                )}
                {state === "failed-inferred" && execution.error && !result?.error && (
                  <p className="mt-1 text-xs text-destructive/70">{execution.error}</p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Summary footer (success) */}
      {execution.summary && (
        <div className="px-4 py-3 border-t border-white/10">
          <p className="text-xs text-smoke/80 uppercase tracking-wide mb-1">Summary</p>
          <p className="text-sm text-white/80 whitespace-pre-wrap">{execution.summary}</p>
        </div>
      )}

      {/* Error footer (failure without a per-step error already shown) */}
      {failed && execution.error && !execution.summary && completedCount < workflow.steps.length && (
        <div className="px-4 py-3 border-t border-destructive/20">
          <p className="text-xs text-destructive font-medium mb-0.5">Failure reason</p>
          <p className="text-xs text-destructive/80">{execution.error}</p>
        </div>
      )}
    </div>
  );
}
