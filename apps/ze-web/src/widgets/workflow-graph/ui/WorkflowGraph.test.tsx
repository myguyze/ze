import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import type { WorkflowStepResponse, WorkflowExecutionResponse } from "@myguyze/ze-client";
import { WorkflowGraph } from "./WorkflowGraph";

function step(overrides: Partial<WorkflowStepResponse> & { task: string; id: string }): WorkflowStepResponse {
  return {
    agent_hint: null,
    verify: null,
    branches: [],
    default_next: null,
    ...overrides,
  };
}

function execution(overrides: Partial<WorkflowExecutionResponse>): WorkflowExecutionResponse {
  return {
    id: "exec-1",
    workflow_id: "wf-1",
    status: "completed",
    step_results: [],
    error: null,
    summary: null,
    started_at: null,
    completed_at: null,
    created_at: "2026-07-10T00:00:00.000Z",
    steps_snapshot: [],
    ...overrides,
  };
}

describe("WorkflowGraph", () => {
  it("renders an empty state when there are no steps", () => {
    render(<WorkflowGraph steps={[]} />);
    expect(screen.getByText("No steps defined.")).toBeInTheDocument();
  });

  it("renders every step as a node with a branching, executed workflow", () => {
    const steps = [
      step({
        task: "Check status",
        id: "s0",
        branches: [{ condition: "ok", to: "s2" }, { condition: "fail", to: "s1" }],
      }),
      step({ task: "Retry path", id: "s1" }),
      step({ task: "Success path", id: "s2" }),
    ];
    const ex = execution({
      status: "completed",
      step_results: [
        { step_index: 0, task: "Check status", output: "ok", success: true, error: null, duration_ms: 5, step_id: "s0", branch_taken: "ok" },
        { step_index: 1, task: "Success path", output: "done", success: true, error: null, duration_ms: 5, step_id: "s2", branch_taken: null },
      ],
    });

    render(<WorkflowGraph steps={steps} execution={ex} />);

    expect(screen.getByText("Check status")).toBeInTheDocument();
    expect(screen.getByText("Retry path")).toBeInTheDocument();
    expect(screen.getByText("Success path")).toBeInTheDocument();
    expect(screen.getByText("Not taken this run")).toBeInTheDocument();
  });
});
