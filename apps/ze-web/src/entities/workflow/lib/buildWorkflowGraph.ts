import type { WorkflowStepResponse, WorkflowExecutionResponse, StepResultResponse } from "@myguyze/ze-client";

export type StepState = "completed-ok" | "completed-fail" | "running" | "failed-inferred" | "pending" | "not-taken";

export interface WorkflowGraphNode {
  id: string;
  step: WorkflowStepResponse;
  state: StepState;
  result?: StepResultResponse;
}

export interface WorkflowGraphEdge {
  id: string;
  from: string;
  to: string;
  label: string | null;
  taken: boolean;
}

/**
 * Mirrors the backend's FR-004/FR-005 fallback order: a matching branch wins; else
 * `default_next`; else — since plain sequential steps encode adjacency purely via
 * array order, with no explicit `default_next` — the next step in authored order.
 */
function computeNextStepId(
  step: WorkflowStepResponse,
  index: number,
  steps: WorkflowStepResponse[],
  branchTaken: string | null,
): string | null {
  if (branchTaken) {
    const branch = step.branches.find((b) => b.condition === branchTaken);
    if (branch) return branch.to;
  }
  if (step.default_next) return step.default_next;
  if (step.branches.length === 0) return steps[index + 1]?.id ?? null;
  return null;
}

function buildEdges(steps: WorkflowStepResponse[]): WorkflowGraphEdge[] {
  const edges: WorkflowGraphEdge[] = [];
  steps.forEach((step, index) => {
    for (const branch of step.branches) {
      edges.push({
        id: `${step.id}->${branch.to}:${branch.condition}`,
        from: step.id,
        to: branch.to,
        label: branch.condition,
        taken: false,
      });
    }
    if (step.default_next) {
      edges.push({
        id: `${step.id}->${step.default_next}:default`,
        from: step.id,
        to: step.default_next,
        label: step.branches.length > 0 ? "default" : null,
        taken: false,
      });
    } else if (step.branches.length === 0) {
      const next = steps[index + 1];
      if (next) {
        edges.push({
          id: `${step.id}->${next.id}:next`,
          from: step.id,
          to: next.id,
          label: null,
          taken: false,
        });
      }
    }
  });
  return edges;
}

/**
 * Builds the full graph shape (every authored step + branch, regardless of whether it
 * ran) plus, when an execution is supplied, per-node status and per-edge "taken"
 * derived from the actual path (branch_taken / default_next), not just execution order.
 */
export function buildWorkflowGraph(
  steps: WorkflowStepResponse[],
  execution: WorkflowExecutionResponse | null,
): { nodes: WorkflowGraphNode[]; edges: WorkflowGraphEdge[] } {
  const stepsById = new Map(steps.map((s) => [s.id, s]));
  const stepIndexById = new Map(steps.map((s, i) => [s.id, i]));
  const edges = buildEdges(steps);

  if (!execution) {
    return {
      nodes: steps.map((step) => ({ id: step.id, step, state: "pending" })),
      edges,
    };
  }

  const lastResultByStep = new Map<string, StepResultResponse>();
  for (const result of execution.step_results) {
    lastResultByStep.set(result.step_id, result);
  }

  // Mark every edge actually traversed so far (including the in-progress hop to
  // whatever step is currently running).
  for (const result of execution.step_results) {
    const step = stepsById.get(result.step_id);
    const index = stepIndexById.get(result.step_id);
    if (!step || index === undefined) continue;
    const targetId = computeNextStepId(step, index, steps, result.branch_taken);
    if (!targetId) continue;
    const edge = edges.find(
      (e) =>
        e.from === result.step_id &&
        e.to === targetId &&
        (!result.branch_taken || e.label === result.branch_taken),
    );
    if (edge) edge.taken = true;
  }

  const lastResult = execution.step_results[execution.step_results.length - 1];
  let nextId: string | null = null;
  if (lastResult) {
    const lastStep = stepsById.get(lastResult.step_id);
    const lastIndex = stepIndexById.get(lastResult.step_id);
    nextId = lastStep && lastIndex !== undefined ? computeNextStepId(lastStep, lastIndex, steps, lastResult.branch_taken) : null;
  } else if (execution.status === "running") {
    nextId = steps[0]?.id ?? null;
  }

  const nodes: WorkflowGraphNode[] = steps.map((step) => {
    const result = lastResultByStep.get(step.id);
    if (result) {
      return { id: step.id, step, state: result.success ? "completed-ok" : "completed-fail", result };
    }
    if (step.id === nextId) {
      if (execution.status === "running") return { id: step.id, step, state: "running" };
      if (execution.status === "failed") return { id: step.id, step, state: "failed-inferred" };
    }
    return { id: step.id, step, state: "not-taken" };
  });

  return { nodes, edges };
}
