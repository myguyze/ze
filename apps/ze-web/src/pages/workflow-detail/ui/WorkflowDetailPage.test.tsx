import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { WorkflowDetailResponse, WorkflowExecutionResponse } from "@myguyze/ze-client";

vi.mock("@/entities/workflow", () => ({
  useWorkflowDetailQuery: vi.fn(),
  useWorkflowExecutionsQuery: vi.fn(),
  useLiveExecutionQuery: vi.fn(),
  useTriggerWorkflowMutation: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useCancelExecutionMutation: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  formatSchedule: vi.fn(() => "On demand"),
  averageSuccessfulRunDuration: vi.fn(() => null),
  stepsDifferFromSnapshot: vi.fn((current, snapshot) => current[0]?.task !== snapshot[0]?.task),
}));

vi.mock("@/features/open-context-overlay", () => ({
  useOverlayStore: vi.fn((selector: (state: { openForExecution: () => void }) => unknown) =>
    selector({ openForExecution: vi.fn() }),
  ),
}));

vi.mock("@/shared/lib", () => ({
  useSetBreadcrumbTitle: vi.fn(),
  cn: (...classes: string[]) => classes.filter(Boolean).join(" "),
  motion: { colors: "" },
}));

vi.mock("@/widgets/workflow-graph", () => ({
  WorkflowGraph: ({ steps }: { steps: { task: string }[] }) => (
    <div data-testid="workflow-graph">{steps.map((step) => step.task).join(", ")}</div>
  ),
  WorkflowDefinitionNotice: ({ mode }: { mode: string }) => (
    <div data-testid="definition-notice">{mode}</div>
  ),
}));

import {
  useWorkflowDetailQuery,
  useWorkflowExecutionsQuery,
  useLiveExecutionQuery,
} from "@/entities/workflow";
import { WorkflowDetailPage } from "./WorkflowDetailPage";

const detail: WorkflowDetailResponse = {
  id: "wf-1",
  name: "Daily check",
  description: "Checks inbox",
  schedule: null,
  enabled: true,
  last_run_at: null,
  next_run_at: null,
  created_at: "2026-07-10T00:00:00.000Z",
  steps: [
    {
      id: "s0",
      task: "Current step",
      agent_hint: null,
      verify: null,
      intent: "execute",
      branches: [],
      default_next: null,
      on_failure: "fail",
    },
  ],
};

function execution(overrides: Partial<WorkflowExecutionResponse>): WorkflowExecutionResponse {
  return {
    id: "exec-1",
    workflow_id: "wf-1",
    status: "completed",
    step_results: [],
    steps_snapshot: [],
    error: null,
    summary: null,
    started_at: "2026-07-09T12:00:00.000Z",
    completed_at: "2026-07-09T12:05:00.000Z",
    created_at: "2026-07-09T12:00:00.000Z",
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/workflows/wf-1"]}>
      <Routes>
        <Route path="/workflows/:workflowId" element={<WorkflowDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("WorkflowDetailPage definition notices", () => {
  beforeEach(() => {
    vi.mocked(useWorkflowDetailQuery).mockReturnValue({
      data: detail,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    } as never);
    vi.mocked(useLiveExecutionQuery).mockReturnValue({
      data: null,
    } as never);
    vi.mocked(useWorkflowExecutionsQuery).mockReturnValue({
      data: [],
      isLoading: false,
    } as never);
  });

  it("shows current definition mode when no run is selected", () => {
    renderPage();
    expect(screen.getByTestId("definition-notice")).toHaveTextContent("current");
    expect(screen.getByTestId("workflow-graph")).toHaveTextContent("Current step");
  });

  it("shows edited-since banner and snapshot graph for historical runs", async () => {
    const historical = execution({
      steps_snapshot: [
        {
          id: "s0",
          task: "Original step",
          agent_hint: null,
          verify: null,
          intent: "execute",
          branches: [],
          default_next: null,
          on_failure: "fail",
        },
      ],
    });

    vi.mocked(useWorkflowExecutionsQuery).mockReturnValue({
      data: [historical],
      isLoading: false,
    } as never);

    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /completed/i }));

    expect(screen.getByTestId("definition-notice")).toHaveTextContent("historical-edited-since");
    expect(screen.getByTestId("workflow-graph")).toHaveTextContent("Original step");
    expect(screen.getByTestId("workflow-graph")).not.toHaveTextContent("Current step");
  });
});
