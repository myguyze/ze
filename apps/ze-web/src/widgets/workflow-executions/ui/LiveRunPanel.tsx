import type { WorkflowDetailResponse, WorkflowExecutionResponse, WorkflowStepResponse } from "@myguyze/ze-client";
import { CheckCircle2, XCircle, Loader2, Circle, CircleSlash } from "lucide-react";

type StepState = "completed-ok" | "completed-fail" | "running" | "failed-inferred" | "pending" | "not-taken";

type StepResult = WorkflowExecutionResponse["step_results"][number];

interface Row {
  key: string;
  step: WorkflowStepResponse;
  state: StepState;
  result?: StepResult;
}

const RUNNING_PLACEHOLDER_STEP: WorkflowStepResponse = {
  task: "Running next step…",
  agent_hint: null,
  verify: null,
  id: "",
  branches: [],
  default_next: null,
};

const FAILED_PLACEHOLDER_STEP: WorkflowStepResponse = {
  task: "Step failed",
  agent_hint: null,
  verify: null,
  id: "",
  branches: [],
  default_next: null,
};

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

/**
 * Builds the row list for a workflow that has at least one branching step. Execution
 * order (not authored order) is source of truth, so a looped step appears once per
 * visit and a step skipped by branching is distinguishable from one not yet reached.
 */
function buildBranchingRows(
  steps: WorkflowStepResponse[],
  execution: WorkflowExecutionResponse,
): Row[] {
  const stepsById = new Map(steps.map((s) => [s.id, s]));
  const executedIds = new Set(execution.step_results.map((r) => r.step_id));

  const rows: Row[] = execution.step_results.map((r, idx) => ({
    key: `${r.step_id}-${idx}`,
    step: stepsById.get(r.step_id) ?? { ...RUNNING_PLACEHOLDER_STEP, task: r.task, id: r.step_id },
    state: r.success ? "completed-ok" : "completed-fail",
    result: r,
  }));

  if (execution.status === "running") {
    rows.push({ key: "running", step: RUNNING_PLACEHOLDER_STEP, state: "running" });
    return rows;
  }

  if (execution.status === "failed") {
    const lastResult = execution.step_results[execution.step_results.length - 1];
    if (!lastResult || lastResult.success) {
      rows.push({ key: "failed-inferred", step: FAILED_PLACEHOLDER_STEP, state: "failed-inferred" });
    }
  }

  for (const step of steps) {
    if (!executedIds.has(step.id)) {
      rows.push({ key: `not-taken-${step.id}`, step, state: "not-taken" });
    }
  }

  return rows;
}

interface Props {
  execution: WorkflowExecutionResponse;
  workflow: WorkflowDetailResponse;
}

export function LiveRunPanel({ execution, workflow }: Props) {
  const isRunning = execution.status === "running";
  const failed = execution.status === "failed";
  const completedCount = execution.step_results.length;
  const hasBranching = workflow.steps.some((s) => s.branches.length > 0);

  const rows: Row[] = hasBranching
    ? buildBranchingRows(workflow.steps, execution)
    : workflow.steps.map((step, i) => ({
        key: `${i}`,
        step,
        state: resolveStepState(i, execution.step_results, execution.status),
        result: execution.step_results.find((r) => r.step_index === i),
      }));

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
            {hasBranching ? `Step ${completedCount + 1}…` : `Step ${completedCount + 1} / ${workflow.steps.length}`}
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
        {rows.map((row) => {
          const { step, state, result } = row;

          return (
            <div key={row.key} className="flex gap-3">
              <div className="flex-shrink-0 mt-0.5">
                {state === "completed-ok" && <CheckCircle2 className="w-4 h-4 text-success" />}
                {state === "completed-fail" && <XCircle className="w-4 h-4 text-destructive" />}
                {state === "failed-inferred" && <XCircle className="w-4 h-4 text-destructive/60" />}
                {state === "running" && <Loader2 className="w-4 h-4 text-plum-voltage animate-spin" />}
                {state === "pending" && <Circle className="w-4 h-4 text-white/20" />}
                {state === "not-taken" && <CircleSlash className="w-4 h-4 text-white/20" />}
              </div>
              <div className="flex-1 min-w-0">
                <p className={`text-sm ${
                  state === "pending" ? "text-white/30"
                  : state === "failed-inferred" ? "text-white/50"
                  : state === "not-taken" ? "text-white/30"
                  : "text-white"
                }`}>
                  {step.task}
                  {state === "not-taken" && (
                    <span className="ml-2 text-xs text-white/25 italic">Not taken this run</span>
                  )}
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
