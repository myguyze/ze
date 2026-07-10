import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import type { WorkflowDetailResponse, WorkflowExecutionResponse, WorkflowStepResponse } from "@myguyze/ze-client";
import { LiveRunPanel } from "./LiveRunPanel";

function step(overrides: Partial<WorkflowStepResponse> & { task: string; id: string }): WorkflowStepResponse {
  return {
    agent_hint: null,
    verify: null,
    branches: [],
    default_next: null,
    ...overrides,
  };
}

function workflow(steps: WorkflowStepResponse[]): WorkflowDetailResponse {
  return {
    id: "wf-1",
    name: "Test workflow",
    description: "",
    schedule: null,
    enabled: true,
    last_run_at: null,
    next_run_at: null,
    created_at: "2026-07-10T00:00:00.000Z",
    steps,
  };
}

function execution(overrides: Partial<WorkflowExecutionResponse>): WorkflowExecutionResponse {
  return {
    id: "exec-1",
    workflow_id: "wf-1",
    status: "running",
    step_results: [],
    error: null,
    summary: null,
    started_at: null,
    completed_at: null,
    created_at: "2026-07-10T00:00:00.000Z",
    ...overrides,
  };
}

describe("LiveRunPanel", () => {
  it("shows the fixed 'N / total' header for a workflow with no branches", () => {
    const wf = workflow([step({ task: "Step one", id: "s0" }), step({ task: "Step two", id: "s1" })]);
    const ex = execution({
      status: "running",
      step_results: [
        { step_index: 0, task: "Step one", output: "a", success: true, error: null, duration_ms: 5, step_id: "s0", branch_taken: null },
      ],
    });

    render(<LiveRunPanel execution={ex} workflow={wf} />);

    expect(screen.getByText("Step 2 / 2")).toBeInTheDocument();
  });

  it("shows a running-count-only header (no denominator) for a workflow with any branching step", () => {
    const wf = workflow([
      step({ task: "Check status", id: "s0", branches: [{ condition: "ok", to: "s1" }] }),
      step({ task: "Notify", id: "s1" }),
    ]);
    const ex = execution({
      status: "running",
      step_results: [
        { step_index: 0, task: "Check status", output: "ok", success: true, error: null, duration_ms: 5, step_id: "s0", branch_taken: "ok" },
      ],
    });

    render(<LiveRunPanel execution={ex} workflow={wf} />);

    expect(screen.getByText("Step 2…")).toBeInTheDocument();
    expect(screen.queryByText(/\/ 2/)).not.toBeInTheDocument();
  });
});
