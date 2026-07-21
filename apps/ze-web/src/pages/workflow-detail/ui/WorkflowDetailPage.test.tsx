import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { WorkflowDetailResponse, WorkflowExecutionResponse, WorkflowRevisionResponse } from "@myguyze/ze-client";

vi.mock("@/entities/workflow", () => ({
  useWorkflowDetailQuery: vi.fn(),
  useWorkflowExecutionsQuery: vi.fn(),
  useWorkflowRevisionsQuery: vi.fn(),
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

const mockSelectSession = vi.fn();
const mockSetHighlightMessage = vi.fn();

function useSessionMock() {
  return { threadId: "test", highlightMessageId: null };
}
useSessionMock.getState = () => ({
  selectSession: mockSelectSession,
  setHighlightMessage: mockSetHighlightMessage,
});

vi.mock("@/entities/session", () => ({
  useSession: useSessionMock,
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
  useWorkflowRevisionsQuery,
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
    vi.mocked(useWorkflowRevisionsQuery).mockReturnValue({
      data: [],
      isLoading: false,
    } as never);
    mockSelectSession.mockClear();
    mockSetHighlightMessage.mockClear();
  });

  it("renders loading state without crashing when detail is undefined", () => {
    vi.mocked(useWorkflowDetailQuery).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      refetch: vi.fn(),
    } as never);

    expect(() => renderPage()).not.toThrow();
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

function revision(overrides: Partial<WorkflowRevisionResponse>): WorkflowRevisionResponse {
  return {
    id: "rev-1",
    workflow_id: "wf-1",
    revision_number: 1,
    change_type: "created",
    steps_before: [],
    steps_after: [],
    summary: "Workflow created with 1 step(s)",
    actor_source: "agent",
    actor_session_id: "sess-1",
    actor_user_message_id: "msg-1",
    created_at: "2026-07-10T00:00:00.000Z",
    ...overrides,
  };
}

describe("WorkflowDetailPage change history", () => {
  beforeEach(() => {
    vi.mocked(useWorkflowDetailQuery).mockReturnValue({
      data: detail,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    } as never);
    vi.mocked(useLiveExecutionQuery).mockReturnValue({ data: null } as never);
    vi.mocked(useWorkflowExecutionsQuery).mockReturnValue({ data: [], isLoading: false } as never);
    mockSelectSession.mockClear();
    mockSetHighlightMessage.mockClear();
  });

  it("shows an explicit empty state when there are no revisions", () => {
    vi.mocked(useWorkflowRevisionsQuery).mockReturnValue({ data: [], isLoading: false } as never);

    renderPage();

    expect(screen.getByText(/No changes recorded yet/i)).toBeInTheDocument();
  });

  it("renders revision entries newest-first with number, badge, actor, and summary", () => {
    vi.mocked(useWorkflowRevisionsQuery).mockReturnValue({
      data: [
        revision({
          id: "rev-2",
          revision_number: 2,
          change_type: "edited",
          summary: "Step s0: on_failure fail → continue",
          actor_source: "api",
          actor_session_id: null,
          actor_user_message_id: null,
        }),
        revision({ id: "rev-1", revision_number: 1 }),
      ],
      isLoading: false,
    } as never);

    renderPage();

    expect(screen.getByText("#2")).toBeInTheDocument();
    expect(screen.getByText("#1")).toBeInTheDocument();
    expect(screen.getByText("edited")).toBeInTheDocument();
    expect(screen.getByText("API")).toBeInTheDocument();
    expect(screen.getByText("Step s0: on_failure fail → continue")).toBeInTheDocument();
  });

  it("expands a revision to show before/after steps", () => {
    vi.mocked(useWorkflowRevisionsQuery).mockReturnValue({
      data: [
        revision({
          change_type: "edited",
          steps_before: [
            { id: "s0", task: "Old task", agent_hint: null, verify: null, branches: [], default_next: null, on_failure: "fail" },
          ],
          steps_after: [
            { id: "s0", task: "New task", agent_hint: null, verify: null, branches: [], default_next: null, on_failure: "fail" },
          ],
        }),
      ],
      isLoading: false,
    } as never);

    renderPage();
    fireEvent.click(screen.getByText("#1"));

    expect(screen.getByText(/Old task/)).toBeInTheDocument();
    expect(screen.getByText(/New task/)).toBeInTheDocument();
  });

  it("shows View conversation only for agent-attributed revisions", () => {
    vi.mocked(useWorkflowRevisionsQuery).mockReturnValue({
      data: [
        revision({ id: "rev-agent", actor_source: "agent" }),
        revision({ id: "rev-api", actor_source: "api", actor_session_id: null, actor_user_message_id: null }),
      ],
      isLoading: false,
    } as never);

    renderPage();

    const links = screen.getAllByText("View conversation");
    expect(links).toHaveLength(1);
  });

  it("navigates to chat and sets highlight when View conversation is clicked", () => {
    vi.mocked(useWorkflowRevisionsQuery).mockReturnValue({
      data: [revision({ actor_session_id: "sess-42", actor_user_message_id: "msg-42" })],
      isLoading: false,
    } as never);

    renderPage();
    fireEvent.click(screen.getByText("View conversation"));

    expect(mockSelectSession).toHaveBeenCalledWith("sess-42");
    expect(mockSetHighlightMessage).toHaveBeenCalledWith("msg-42");
  });
});
