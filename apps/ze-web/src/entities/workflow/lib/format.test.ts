import { describe, expect, it } from "vitest";
import type { WorkflowExecutionResponse } from "@myguyze/ze-client";
import {
  averageSuccessfulRunDuration,
  executionDurationMs,
  formatDurationMs,
} from "./format";

function execution(
  overrides: Partial<WorkflowExecutionResponse> & Pick<WorkflowExecutionResponse, "status">,
): WorkflowExecutionResponse {
  return {
    id: "exec-1",
    workflow_id: "wf-1",
    step_results: [],
    steps_snapshot: [],
    error: null,
    summary: null,
    started_at: "2026-07-01T19:20:00.000Z",
    completed_at: "2026-07-01T19:24:00.000Z",
    created_at: "2026-07-01T19:20:00.000Z",
    ...overrides,
  };
}

describe("executionDurationMs", () => {
  it("returns null when timestamps are missing", () => {
    expect(executionDurationMs(null, "2026-07-01T19:24:00.000Z")).toBeNull();
    expect(executionDurationMs("2026-07-01T19:20:00.000Z", null)).toBeNull();
  });

  it("returns duration in milliseconds", () => {
    expect(
      executionDurationMs("2026-07-01T19:20:00.000Z", "2026-07-01T19:24:00.000Z"),
    ).toBe(240_000);
  });
});

describe("formatDurationMs", () => {
  it("formats sub-second, second, and minute durations", () => {
    expect(formatDurationMs(850)).toBe("850ms");
    expect(formatDurationMs(4_500)).toBe("4.5s");
    expect(formatDurationMs(240_000)).toBe("4m");
    expect(formatDurationMs(255_000)).toBe("4m 15s");
  });
});

describe("averageSuccessfulRunDuration", () => {
  it("returns null when there are no successful runs", () => {
    expect(averageSuccessfulRunDuration([
      execution({ status: "failed" }),
      execution({ status: "running", completed_at: null }),
    ])).toBeNull();
  });

  it("averages only completed runs with timestamps", () => {
    expect(averageSuccessfulRunDuration([
      execution({ status: "completed" }),
      execution({
        status: "completed",
        started_at: "2026-07-01T19:20:00.000Z",
        completed_at: "2026-07-01T19:28:00.000Z",
      }),
      execution({ status: "failed" }),
    ])).toBe("6m");
  });
});
