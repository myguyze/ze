import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Workflow, Loader2, CheckCircle2, XCircle, MessageCircle, Ban, ChevronDown, ChevronRight } from "lucide-react";
import { useOverlayStore } from "@/features/open-context-overlay";
import { useSetBreadcrumbTitle } from "@/shared/lib";
import { useSession } from "@/entities/session";
import ReactMarkdown from "react-markdown";
import type { WorkflowExecutionResponse, WorkflowRevisionResponse, WorkflowStepResponse } from "@myguyze/ze-client";
import {
  useWorkflowDetailQuery,
  useWorkflowExecutionsQuery,
  useWorkflowRevisionsQuery,
  useLiveExecutionQuery,
  useTriggerWorkflowMutation,
  useCancelExecutionMutation,
  formatSchedule,
  averageSuccessfulRunDuration,
  stepsDifferFromSnapshot,
} from "@/entities/workflow";
import { WorkflowGraph, WorkflowDefinitionNotice, type WorkflowDefinitionNoticeMode } from "@/widgets/workflow-graph";
import { WorkflowExecutionsList } from "@/widgets/workflow-executions";
import { ListSkeleton, ErrorState, Button, PageShell, SectionPanel } from "@/shared/ui";

export function WorkflowDetailPage() {
  const { workflowId } = useParams<{ workflowId: string }>();
  const navigate = useNavigate();
  const [liveExecutionId, setLiveExecutionId] = useState<string | null>(null);
  const [selectedExecution, setSelectedExecution] = useState<WorkflowExecutionResponse | null>(null);

  const { data: detail, isLoading, isError, refetch } = useWorkflowDetailQuery(workflowId ?? "");
  const { data: executions, isLoading: execLoading } = useWorkflowExecutionsQuery(workflowId ?? "");
  const { data: revisions, isLoading: revisionsLoading } = useWorkflowRevisionsQuery(workflowId ?? "");
  const { data: liveExecution } = useLiveExecutionQuery(workflowId ?? "", liveExecutionId);
  const [revisionsSinceFilter, setRevisionsSinceFilter] = useState<string | null>(null);

  const trigger = useTriggerWorkflowMutation();
  const cancelExecution = useCancelExecutionMutation();

  useSetBreadcrumbTitle(detail?.name);

  const avgRunDuration = executions ? averageSuccessfulRunDuration(executions) : null;

  const displayExecution: WorkflowExecutionResponse | null | undefined =
    selectedExecution ?? liveExecution;

  const isRunning =
    trigger.isPending ||
    liveExecution?.status === "running" ||
    displayExecution?.status === "running";

  const displayedId = displayExecution?.id ?? null;
  const activeExecutionId =
    liveExecutionId ?? (liveExecution?.status === "running" ? liveExecution.id : null);

  function handleTrigger() {
    if (!workflowId) return;
    setSelectedExecution(null);
    trigger.mutate(workflowId, {
      onSuccess: (data) => {
        setLiveExecutionId(data.execution_id);
      },
    });
  }

  function handleCancel() {
    if (!workflowId || !activeExecutionId) return;
    cancelExecution.mutate({ workflowId, executionId: activeExecutionId });
  }

  function handleSelectExecution(ex: WorkflowExecutionResponse) {
    setSelectedExecution(ex);
  }

  if (isLoading) {
    return (
      <PageShell className="max-w-5xl mx-auto">
        <ListSkeleton count={4} />
      </PageShell>
    );
  }

  if (isError || !detail) {
    return (
      <PageShell className="max-w-5xl mx-auto">
        <ErrorState message="Could not load workflow." onRetry={() => void refetch()} />
      </PageShell>
    );
  }

  const definitionNoticeMode = resolveDefinitionNoticeMode(displayExecution, detail.steps);
  const graphSteps = resolveGraphSteps(displayExecution, detail.steps);

  return (
    <PageShell className="max-w-5xl mx-auto">
      {/* Header */}
      <div>
        <button
          className="flex items-center gap-1.5 text-xs text-smoke hover:text-white transition-colors mb-6"
          onClick={() => navigate("/workflows")}
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Workflows
        </button>

        <div className="flex items-start justify-between gap-6">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-xl bg-plum-voltage/10 border border-plum-voltage/20 flex items-center justify-center flex-shrink-0 mt-0.5">
              <Workflow className="w-5 h-5 text-plum-voltage" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-white leading-tight">{detail.name}</h1>
              {detail.description && (
                <p className="text-sm text-smoke/80 mt-2 leading-relaxed max-w-2xl">{detail.description}</p>
              )}
              <div className="flex flex-wrap items-center gap-2 mt-4">
                <span
                  className={
                    detail.enabled
                      ? "inline-block px-2.5 py-0.5 rounded-full border border-plum-voltage/50 text-plum-voltage text-xs"
                      : "inline-block px-2.5 py-0.5 rounded-full border border-white/20 text-smoke text-xs"
                  }
                >
                  {detail.enabled ? "active" : "paused"}
                </span>
                <span className="inline-block px-2.5 py-0.5 rounded-full border border-white/15 text-smoke text-xs">
                  {formatSchedule(detail.schedule)}
                </span>
                {avgRunDuration && (
                  <span className="inline-block px-2.5 py-0.5 rounded-full border border-white/15 text-smoke text-xs">
                    {avgRunDuration} avg run
                  </span>
                )}
              </div>
            </div>
          </div>

          {detail.enabled && (
            <div className="flex items-center gap-2">
              {isRunning && activeExecutionId && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={cancelExecution.isPending}
                  onClick={handleCancel}
                >
                  {cancelExecution.isPending ? "Cancelling…" : "Cancel"}
                </Button>
              )}
              <Button
                size="sm"
                variant="outline"
                disabled={isRunning}
                onClick={handleTrigger}
              >
                {trigger.isPending ? "Starting…" : "Run now"}
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* Main layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Steps — 2/3 width */}
        <SectionPanel className="lg:col-span-2">
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-xs font-semibold text-white/40 uppercase tracking-widest">Steps</h2>
            <div className="flex items-center gap-2">
              <StepsStatus
                liveExecution={liveExecution}
                displayExecution={displayExecution}
                isRunning={isRunning}
                onClear={() => {
                  setLiveExecutionId(null);
                  setSelectedExecution(null);
                }}
              />
              {displayExecution && !isRunning && (
                <ChatAboutRunButton execution={displayExecution} workflowName={detail.name} />
              )}
            </div>
          </div>

          <WorkflowDefinitionNotice
            mode={definitionNoticeMode}
            startedAt={displayExecution?.started_at}
            onViewRevisionsSince={
              displayExecution?.started_at
                ? () => {
                    setRevisionsSinceFilter(displayExecution.started_at ?? null);
                    document
                      .getElementById("change-history")
                      ?.scrollIntoView({ behavior: "smooth", block: "start" });
                  }
                : undefined
            }
          />

          <WorkflowGraph steps={graphSteps} execution={displayExecution} isLive={isRunning} />

          {displayExecution?.summary && displayExecution.status !== "running" && (
            <div className="mt-5 pt-5 border-t border-white/[0.06]">
              <p className="text-xs font-semibold text-white/40 uppercase tracking-widest mb-3">Summary</p>
              <div className="text-sm text-white/80 leading-relaxed space-y-1.5">
                <ReactMarkdown
                  components={{
                    h1: ({ children }) => <p className="font-semibold text-white mt-3 mb-1 text-base">{children}</p>,
                    h2: ({ children }) => <p className="font-semibold text-white/90 mt-3 mb-1">{children}</p>,
                    h3: ({ children }) => <p className="font-medium text-white/80 mt-2 mb-0.5">{children}</p>,
                    p: ({ children }) => <p className="mb-2">{children}</p>,
                    strong: ({ children }) => <strong className="text-white font-medium">{children}</strong>,
                    ul: ({ children }) => <ul className="list-disc pl-5 mb-2 space-y-0.5">{children}</ul>,
                    ol: ({ children }) => <ol className="list-decimal pl-5 mb-2 space-y-0.5">{children}</ol>,
                    li: ({ children }) => <li className="text-white/80">{children}</li>,
                    code: ({ children }) => <code className="bg-white/10 rounded px-1.5 py-0.5 text-xs font-mono">{children}</code>,
                    blockquote: ({ children }) => (
                      <blockquote className="border-l-2 border-white/20 pl-3 italic text-white/60 my-2">{children}</blockquote>
                    ),
                    hr: () => <hr className="border-white/10 my-3" />,
                  }}
                >
                  {displayExecution.summary}
                </ReactMarkdown>
              </div>
            </div>
          )}
        </SectionPanel>

        {/* Run history + change history sidebar */}
        <div className="flex flex-col gap-6">
          <SectionPanel>
            <h2 className="text-xs font-semibold text-white/40 uppercase tracking-widest mb-5">Run History</h2>
            {execLoading ? (
              <ListSkeleton count={3} />
            ) : (
              <WorkflowExecutionsList
                executions={executions ?? []}
                selectedId={displayedId}
                onSelect={handleSelectExecution}
              />
            )}
          </SectionPanel>

          <div id="change-history">
            <SectionPanel>
              <h2 className="text-xs font-semibold text-white/40 uppercase tracking-widest mb-5">Change History</h2>
              {revisionsLoading ? (
                <ListSkeleton count={3} />
              ) : (
                <ChangeHistoryList
                  revisions={revisions ?? []}
                  sinceFilter={revisionsSinceFilter}
                  onClearFilter={() => setRevisionsSinceFilter(null)}
                />
              )}
            </SectionPanel>
          </div>
        </div>
      </div>
    </PageShell>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function formatDuration(startedAt: string | null, completedAt: string | null): string {
  if (!startedAt || !completedAt) return "";
  const ms = new Date(completedAt).getTime() - new Date(startedAt).getTime();
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

interface ChatAboutRunButtonProps {
  execution: WorkflowExecutionResponse;
  workflowName: string;
}

function ChatAboutRunButton({ execution, workflowName }: ChatAboutRunButtonProps) {
  const openForExecution = useOverlayStore((s) => s.openForExecution);
  const date = execution.started_at ? formatTimestamp(execution.started_at) : "unknown date";
  const duration = formatDuration(execution.started_at, execution.completed_at);
  const stepCount = execution.step_results.length;
  const status = execution.status === "completed" ? "completed" : "failed";
  const durationPart = duration ? ` in ${duration}` : "";
  const errorPart = execution.error ? `. Error: ${execution.error}` : "";
  const prefillMessage = `Tell me about the "${workflowName}" workflow run from ${date}. It ${status}${durationPart} with ${stepCount} step${stepCount !== 1 ? "s" : ""}${errorPart}.`;

  return (
    <button
      className="flex items-center gap-1.5 text-xs text-smoke hover:text-white transition-colors"
      title="Chat about this run"
      onClick={() => openForExecution({ screen: "workflow run", entityId: execution.id, prefillMessage })}
    >
      <MessageCircle className="w-3.5 h-3.5" />
      Ask Ze
    </button>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function resolveDefinitionNoticeMode(
  displayExecution: WorkflowExecutionResponse | null | undefined,
  currentSteps: WorkflowStepResponse[],
): WorkflowDefinitionNoticeMode {
  if (!displayExecution) return "current";
  const snapshot = displayExecution.steps_snapshot ?? [];
  if (snapshot.length === 0) return "legacy-unavailable";
  if (stepsDifferFromSnapshot(currentSteps, snapshot)) return "historical-edited-since";
  return "historical";
}

function resolveGraphSteps(
  displayExecution: WorkflowExecutionResponse | null | undefined,
  currentSteps: WorkflowStepResponse[],
): WorkflowStepResponse[] {
  if (!displayExecution) return currentSteps;
  const snapshot = displayExecution.steps_snapshot ?? [];
  if (snapshot.length > 0) return snapshot;
  return currentSteps;
}

interface StepsStatusProps {
  liveExecution: WorkflowExecutionResponse | null | undefined;
  displayExecution: WorkflowExecutionResponse | null | undefined;
  isRunning: boolean;
  onClear: () => void;
}

function StepsStatus({ liveExecution, displayExecution, isRunning, onClear }: StepsStatusProps) {
  if (isRunning && liveExecution) {
    return (
      <div className="flex items-center gap-1.5">
        <Loader2 className="w-3.5 h-3.5 text-plum-voltage animate-spin" />
        <span className="text-xs text-plum-voltage">Running…</span>
      </div>
    );
  }

  if (liveExecution && displayExecution?.id === liveExecution.id) {
    if (liveExecution.status === "completed") {
      return (
        <div className="flex items-center gap-1.5">
          <CheckCircle2 className="w-3.5 h-3.5 text-success" />
          <span className="text-xs text-success">Complete</span>
          <button className="ml-1 text-xs text-smoke hover:text-white transition-colors" onClick={onClear}>
            Clear
          </button>
        </div>
      );
    }
    if (liveExecution.status === "cancelled") {
      return (
        <div className="flex items-center gap-1.5">
          <Ban className="w-3.5 h-3.5 text-amber-400" />
          <span className="text-xs text-amber-400">Cancelled</span>
          <button className="ml-1 text-xs text-smoke hover:text-white transition-colors" onClick={onClear}>
            Clear
          </button>
        </div>
      );
    }
    if (liveExecution.status === "failed") {
      return (
        <div className="flex items-center gap-1.5">
          <XCircle className="w-3.5 h-3.5 text-destructive" />
          <span className="text-xs text-destructive">Failed</span>
          <button className="ml-1 text-xs text-smoke hover:text-white transition-colors" onClick={onClear}>
            Clear
          </button>
        </div>
      );
    }
  }

  if (displayExecution && !liveExecution) {
    const status = displayExecution.status;
    const succeeded = status === "completed";
    const cancelled = status === "cancelled";
    return (
      <div className="flex items-center gap-1.5">
        {succeeded ? (
          <CheckCircle2 className="w-3.5 h-3.5 text-success" />
        ) : cancelled ? (
          <Ban className="w-3.5 h-3.5 text-amber-400" />
        ) : (
          <XCircle className="w-3.5 h-3.5 text-destructive" />
        )}
        <span
          className={`text-xs ${
            succeeded ? "text-success" : cancelled ? "text-amber-400" : "text-destructive"
          }`}
        >
          {succeeded ? "Completed" : cancelled ? "Cancelled" : "Failed"}
        </span>
        <button className="ml-1 text-xs text-smoke hover:text-white transition-colors" onClick={onClear}>
          Clear
        </button>
      </div>
    );
  }

  return null;
}

// ── Change History ───────────────────────────────────────────────────────────

function formatRelativeTimestamp(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

function actorLabel(source: WorkflowRevisionResponse["actor_source"]): string {
  return source === "api" ? "API" : "Ze";
}

interface ChangeHistoryListProps {
  revisions: WorkflowRevisionResponse[];
  sinceFilter: string | null;
  onClearFilter: () => void;
}

function ChangeHistoryList({ revisions, sinceFilter, onClearFilter }: ChangeHistoryListProps) {
  const filtered = sinceFilter
    ? revisions.filter((r) => new Date(r.created_at).getTime() > new Date(sinceFilter).getTime())
    : revisions;

  if (revisions.length === 0) {
    return (
      <p className="text-sm text-smoke/70">
        No changes recorded yet. Edits made before this feature shipped aren't shown here.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {sinceFilter && (
        <div className="flex items-center justify-between text-xs text-plum-voltage">
          <span>Showing changes since this run</span>
          <button className="underline underline-offset-2 hover:text-plum-voltage/80" onClick={onClearFilter}>
            Clear filter
          </button>
        </div>
      )}
      {filtered.length === 0 ? (
        <p className="text-sm text-smoke/70">No changes since this run.</p>
      ) : (
        filtered.map((revision) => <WorkflowRevisionRow key={revision.id} revision={revision} />)
      )}
    </div>
  );
}

function WorkflowRevisionRow({ revision }: { revision: WorkflowRevisionResponse }) {
  const [expanded, setExpanded] = useState(false);
  const [conversationUnavailable, setConversationUnavailable] = useState(false);
  const navigate = useNavigate();

  function handleViewConversation() {
    if (!revision.actor_session_id) {
      setConversationUnavailable(true);
      return;
    }
    useSession.getState().selectSession(revision.actor_session_id);
    useSession.getState().setHighlightMessage(revision.actor_user_message_id ?? null);
    navigate("/");
  }

  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
      <button
        className="flex w-full items-start gap-2 text-left"
        onClick={() => setExpanded((v) => !v)}
      >
        {expanded ? (
          <ChevronDown className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-smoke" />
        ) : (
          <ChevronRight className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-smoke" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-white/70">#{revision.revision_number}</span>
            <span
              className={
                revision.change_type === "created"
                  ? "rounded-full border border-plum-voltage/50 px-2 py-0.5 text-plum-voltage"
                  : "rounded-full border border-white/15 px-2 py-0.5 text-smoke"
              }
            >
              {revision.change_type}
            </span>
            <span className="text-smoke">{actorLabel(revision.actor_source)}</span>
            <span className="text-smoke/70">{formatRelativeTimestamp(revision.created_at)}</span>
          </div>
          <p className="mt-1 text-sm text-white/80">{revision.summary || "No fields changed"}</p>
        </div>
      </button>

      {revision.actor_source === "agent" && (
        <div className="mt-2 pl-5.5">
          {conversationUnavailable ? (
            <p className="text-xs text-smoke/70">Conversation unavailable.</p>
          ) : (
            <button
              className="text-xs text-plum-voltage hover:text-plum-voltage/80 underline underline-offset-2"
              onClick={handleViewConversation}
            >
              View conversation
            </button>
          )}
        </div>
      )}

      {expanded && (
        <div className="mt-3 grid grid-cols-1 gap-3 pl-5.5 sm:grid-cols-2">
          <div>
            <p className="mb-1 text-[10px] uppercase tracking-widest text-smoke/60">Before</p>
            <StepSummaryList steps={revision.steps_before} />
          </div>
          <div>
            <p className="mb-1 text-[10px] uppercase tracking-widest text-smoke/60">After</p>
            <StepSummaryList steps={revision.steps_after} />
          </div>
        </div>
      )}
    </div>
  );
}

function StepSummaryList({ steps }: { steps: WorkflowStepResponse[] }) {
  if (steps.length === 0) {
    return <p className="text-xs text-smoke/50">(none)</p>;
  }
  return (
    <ul className="space-y-1">
      {steps.map((step) => (
        <li key={step.id} className="text-xs text-white/70">
          <span className="text-smoke/70">{step.id}</span> {step.task}
          {step.on_failure !== "fail" && (
            <span className="ml-1 text-smoke/60">(on_failure: {step.on_failure})</span>
          )}
        </li>
      ))}
    </ul>
  );
}
