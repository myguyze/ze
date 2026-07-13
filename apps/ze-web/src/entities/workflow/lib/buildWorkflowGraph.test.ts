import { describe, it, expect } from "vitest";
import type { WorkflowExecutionResponse, WorkflowStepResponse } from "@myguyze/ze-client";
import { buildWorkflowGraph } from "./buildWorkflowGraph";

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

describe("buildWorkflowGraph", () => {
  it("chains plain sequential steps (no branches, no default_next) with implicit edges", () => {
    const steps = [
      step({ task: "Find contact", id: "s0" }),
      step({ task: "Create reminder", id: "s1" }),
      step({ task: "Send message", id: "s2" }),
    ];

    const { edges } = buildWorkflowGraph(steps, null);

    expect(edges).toEqual([
      expect.objectContaining({ from: "s0", to: "s1", label: null }),
      expect.objectContaining({ from: "s1", to: "s2", label: null }),
    ]);
  });

  it("marks implicit sequential edges taken as a plain run progresses", () => {
    const steps = [
      step({ task: "Find contact", id: "s0" }),
      step({ task: "Create reminder", id: "s1" }),
      step({ task: "Send message", id: "s2" }),
    ];
    const ex = execution({
      status: "running",
      step_results: [
        { step_index: 0, task: "Find contact", output: "a", success: true, error: null, duration_ms: 5, step_id: "s0", branch_taken: null },
      ],
    });

    const { nodes, edges } = buildWorkflowGraph(steps, ex);

    expect(edges.find((e) => e.from === "s0" && e.to === "s1")?.taken).toBe(true);
    expect(nodes.find((n) => n.id === "s1")?.state).toBe("running");
    expect(nodes.find((n) => n.id === "s2")?.state).toBe("not-taken");
  });

  it("builds every authored branch/default edge regardless of execution", () => {
    const steps = [
      step({
        task: "Check status",
        id: "s0",
        branches: [{ condition: "ok", to: "s2" }, { condition: "fail", to: "s1" }],
      }),
      step({ task: "Retry path", id: "s1" }),
      step({ task: "Success path", id: "s2" }),
    ];

    const { nodes, edges } = buildWorkflowGraph(steps, null);

    expect(nodes).toHaveLength(3);
    expect(nodes.every((n) => n.state === "pending")).toBe(true);
    expect(edges).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ from: "s0", to: "s2", label: "ok", taken: false }),
        expect.objectContaining({ from: "s0", to: "s1", label: "fail", taken: false }),
        // s1 (not the last step) still implicitly chains to s2 since it has no
        // branches/default_next of its own — s0's branches don't affect that.
        expect.objectContaining({ from: "s1", to: "s2", label: null, taken: false }),
      ]),
    );
    expect(edges).toHaveLength(3);
  });

  it("marks the executed branch edge as taken and the skipped branch step as not-taken", () => {
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

    const { nodes, edges } = buildWorkflowGraph(steps, ex);

    const takenEdge = edges.find((e) => e.from === "s0" && e.to === "s2");
    const skippedEdge = edges.find((e) => e.from === "s0" && e.to === "s1");
    expect(takenEdge?.taken).toBe(true);
    expect(skippedEdge?.taken).toBe(false);

    const notTakenNode = nodes.find((n) => n.id === "s1");
    expect(notTakenNode?.state).toBe("not-taken");

    const s0 = nodes.find((n) => n.id === "s0");
    const s2 = nodes.find((n) => n.id === "s2");
    expect(s0?.state).toBe("completed-ok");
    expect(s2?.state).toBe("completed-ok");
  });

  it("uses the default edge (not a labeled branch) when branch_taken is null", () => {
    const steps = [
      step({ task: "Step one", id: "s0", default_next: "s1" }),
      step({ task: "Step two", id: "s1" }),
    ];
    const ex = execution({
      status: "completed",
      step_results: [
        { step_index: 0, task: "Step one", output: "a", success: true, error: null, duration_ms: 5, step_id: "s0", branch_taken: null },
        { step_index: 1, task: "Step two", output: "b", success: true, error: null, duration_ms: 5, step_id: "s1", branch_taken: null },
      ],
    });

    const { nodes, edges } = buildWorkflowGraph(steps, ex);

    expect(edges).toEqual([expect.objectContaining({ from: "s0", to: "s1", label: null, taken: true })]);
    expect(nodes.every((n) => n.state === "completed-ok")).toBe(true);
  });

  it("marks the currently running step by following the last executed transition", () => {
    const steps = [
      step({ task: "Step one", id: "s0", default_next: "s1" }),
      step({ task: "Step two", id: "s1" }),
    ];
    const ex = execution({
      status: "running",
      step_results: [
        { step_index: 0, task: "Step one", output: "a", success: true, error: null, duration_ms: 5, step_id: "s0", branch_taken: null },
      ],
    });

    const { nodes } = buildWorkflowGraph(steps, ex);

    expect(nodes.find((n) => n.id === "s0")?.state).toBe("completed-ok");
    expect(nodes.find((n) => n.id === "s1")?.state).toBe("running");
  });

  it("marks the entry step as running when execution has no results yet", () => {
    const steps = [step({ task: "Step one", id: "s0" }), step({ task: "Step two", id: "s1" })];
    const ex = execution({ status: "running", step_results: [] });

    const { nodes } = buildWorkflowGraph(steps, ex);

    expect(nodes.find((n) => n.id === "s0")?.state).toBe("running");
    expect(nodes.find((n) => n.id === "s1")?.state).toBe("not-taken");
  });

  it("infers a failure on the step that never reported a result", () => {
    const steps = [
      step({ task: "Step one", id: "s0", default_next: "s1" }),
      step({ task: "Step two", id: "s1" }),
    ];
    const ex = execution({
      status: "failed",
      error: "boom",
      step_results: [
        { step_index: 0, task: "Step one", output: "a", success: true, error: null, duration_ms: 5, step_id: "s0", branch_taken: null },
      ],
    });

    const { nodes } = buildWorkflowGraph(steps, ex);

    expect(nodes.find((n) => n.id === "s1")?.state).toBe("failed-inferred");
  });

  it("keeps the latest result for a looped step", () => {
    const steps = [
      step({ task: "Check status", id: "s0", branches: [{ condition: "retry", to: "s0" }] }),
      step({ task: "Notify", id: "s1" }),
    ];
    const ex = execution({
      status: "completed",
      step_results: [
        { step_index: 0, task: "Check status", output: "first attempt", success: false, error: "retry", duration_ms: 5, step_id: "s0", branch_taken: "retry" },
        { step_index: 1, task: "Check status", output: "second attempt", success: true, error: null, duration_ms: 5, step_id: "s0", branch_taken: null },
        { step_index: 2, task: "Notify", output: "done", success: true, error: null, duration_ms: 5, step_id: "s1", branch_taken: null },
      ],
    });

    const { nodes, edges } = buildWorkflowGraph(steps, ex);

    const s0 = nodes.find((n) => n.id === "s0");
    expect(s0?.state).toBe("completed-ok");
    expect(s0?.result?.output).toBe("second attempt");

    const loopEdge = edges.find((e) => e.from === "s0" && e.to === "s0");
    expect(loopEdge?.taken).toBe(true);
  });
});
