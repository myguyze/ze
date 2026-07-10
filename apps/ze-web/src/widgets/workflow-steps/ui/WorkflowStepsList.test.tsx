import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import type { WorkflowExecutionResponse, WorkflowStepResponse } from "@myguyze/ze-client";
import { WorkflowStepsList } from "./WorkflowStepsList";

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
    ...overrides,
  };
}

describe("WorkflowStepsList", () => {
  it("renders looped step results in execution order, keyed by step_id, as separate rows", () => {
    const steps = [
      step({ task: "Check status", id: "s0", branches: [{ condition: "retry", to: "s0" }] }),
      step({ task: "Notify", id: "s1" }),
    ];
    const ex = execution({
      status: "completed",
      step_results: [
        { step_index: 0, task: "Check status", output: "first attempt", success: true, error: null, duration_ms: 5, step_id: "s0", branch_taken: "retry" },
        { step_index: 1, task: "Check status", output: "second attempt", success: true, error: null, duration_ms: 5, step_id: "s0", branch_taken: null },
        { step_index: 2, task: "Notify", output: "done", success: true, error: null, duration_ms: 5, step_id: "s1", branch_taken: null },
      ],
    });

    render(<WorkflowStepsList steps={steps} execution={ex} />);

    expect(screen.getAllByText("Check status")).toHaveLength(2);
    expect(screen.getByText("first attempt")).toBeInTheDocument();
    expect(screen.getByText("second attempt")).toBeInTheDocument();
    expect(screen.getByText("done")).toBeInTheDocument();
  });

  it("renders a step absent from the executed path as not taken this run", () => {
    const steps = [
      step({ task: "Check status", id: "s0", branches: [{ condition: "ok", to: "s2" }, { condition: "fail", to: "s1" }] }),
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

    render(<WorkflowStepsList steps={steps} execution={ex} />);

    expect(screen.getByText("Retry path")).toBeInTheDocument();
    expect(screen.getByText("Not taken this run")).toBeInTheDocument();
    expect(screen.getByText("Success path")).toBeInTheDocument();
  });

  it("shows zero visual change for a non-branching workflow (no not-taken rows, regression)", () => {
    const steps = [
      step({ task: "Step one", id: "s0" }),
      step({ task: "Step two", id: "s1" }),
    ];
    const ex = execution({
      status: "completed",
      step_results: [
        { step_index: 0, task: "Step one", output: "a", success: true, error: null, duration_ms: 5, step_id: "s0", branch_taken: null },
        { step_index: 1, task: "Step two", output: "b", success: true, error: null, duration_ms: 5, step_id: "s1", branch_taken: null },
      ],
    });

    render(<WorkflowStepsList steps={steps} execution={ex} />);

    expect(screen.queryByText("Not taken this run")).not.toBeInTheDocument();
    expect(screen.getByText("Step one")).toBeInTheDocument();
    expect(screen.getByText("Step two")).toBeInTheDocument();
  });
});
