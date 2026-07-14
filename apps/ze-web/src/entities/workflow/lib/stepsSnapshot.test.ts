import { describe, it, expect } from "vitest";
import type { WorkflowStepResponse } from "@myguyze/ze-client";
import { stepsDifferFromSnapshot } from "./stepsSnapshot";

function step(
  overrides: Partial<WorkflowStepResponse> & { task: string; id: string },
): WorkflowStepResponse {
  return {
    agent_hint: null,
    verify: null,
    branches: [],
    default_next: null,
    ...overrides,
  };
}

describe("stepsDifferFromSnapshot", () => {
  it("returns false when current steps match snapshot", () => {
    const steps = [
      step({ task: "First", id: "s0", on_failure: "continue" }),
      step({ task: "Second", id: "s1" }),
    ];
    expect(stepsDifferFromSnapshot(steps, steps)).toBe(false);
  });

  it("returns true when task text differs", () => {
    const current = [step({ task: "Updated", id: "s0" })];
    const snapshot = [step({ task: "Original", id: "s0" })];
    expect(stepsDifferFromSnapshot(current, snapshot)).toBe(true);
  });

  it("returns true when on_failure or branches differ", () => {
    const current = [
      step({
        task: "Check",
        id: "s0",
        on_failure: "fail",
        branches: [{ condition: "ok", to: "s1" }],
      }),
    ];
    const snapshot = [
      step({
        task: "Check",
        id: "s0",
        on_failure: "continue",
        branches: [{ condition: "ok", to: "s1" }],
      }),
    ];
    expect(stepsDifferFromSnapshot(current, snapshot)).toBe(true);
  });
});
