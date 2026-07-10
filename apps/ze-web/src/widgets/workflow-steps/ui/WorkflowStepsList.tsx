import { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import type { WorkflowStepResponse, WorkflowExecutionResponse } from "@myguyze/ze-client";
import { CheckCircle2, XCircle, Loader2, ChevronDown, CircleSlash } from "lucide-react";
import { cn, motion } from "@/shared/lib";

type StepState = "completed-ok" | "completed-fail" | "running" | "failed-inferred" | "pending" | "not-taken";

type StepResult = WorkflowExecutionResponse["step_results"][number];

interface Row {
  key: string;
  step: WorkflowStepResponse;
  state: StepState;
  result?: StepResult;
}

const RUNNING_PLACEHOLDER_STEP: WorkflowStepResponse = {
  task: "Running next step…",
  agent_hint: null,
  verify: null,
  id: "",
  branches: [],
  default_next: null,
};

const FAILED_PLACEHOLDER_STEP: WorkflowStepResponse = {
  task: "Step failed",
  agent_hint: null,
  verify: null,
  id: "",
  branches: [],
  default_next: null,
};

function resolveStepState(
  stepIndex: number,
  stepResults: WorkflowExecutionResponse["step_results"],
  executionStatus: string,
): StepState {
  const result = stepResults.find((r) => r.step_index === stepIndex);
  if (result) return result.success ? "completed-ok" : "completed-fail";

  const completedCount = stepResults.length;

  if (executionStatus === "running") {
    if (stepIndex === completedCount) return "running";
    return "pending";
  }

  if (executionStatus === "failed" && stepIndex === completedCount) return "failed-inferred";
  return "pending";
}

/**
 * Builds the row list for a workflow that has at least one branching step. Execution
 * order (not authored order) is source of truth, so a looped step appears once per
 * visit and a step skipped by branching is distinguishable from one not yet reached.
 */
function buildBranchingRows(
  steps: WorkflowStepResponse[],
  execution: WorkflowExecutionResponse,
): Row[] {
  const stepsById = new Map(steps.map((s) => [s.id, s]));
  const executedIds = new Set(execution.step_results.map((r) => r.step_id));

  const rows: Row[] = execution.step_results.map((r, idx) => ({
    key: `${r.step_id}-${idx}`,
    step: stepsById.get(r.step_id) ?? { ...RUNNING_PLACEHOLDER_STEP, task: r.task, id: r.step_id },
    state: r.success ? "completed-ok" : "completed-fail",
    result: r,
  }));

  if (execution.status === "running") {
    rows.push({ key: "running", step: RUNNING_PLACEHOLDER_STEP, state: "running" });
    return rows;
  }

  if (execution.status === "failed") {
    const lastResult = execution.step_results[execution.step_results.length - 1];
    if (!lastResult || lastResult.success) {
      rows.push({ key: "failed-inferred", step: FAILED_PLACEHOLDER_STEP, state: "failed-inferred" });
    }
  }

  for (const step of steps) {
    if (!executedIds.has(step.id)) {
      rows.push({ key: `not-taken-${step.id}`, step, state: "not-taken" });
    }
  }

  return rows;
}

interface StepRowProps {
  step: WorkflowStepResponse;
  index: number;
  state: StepState;
  result?: WorkflowExecutionResponse["step_results"][number];
  executionError?: string | null;
  isLast: boolean;
  expanded: boolean;
  onToggle: () => void;
}

function StepIcon({ state }: { state: StepState }) {
  if (state === "completed-ok") return <CheckCircle2 className="w-5 h-5 text-success" />;
  if (state === "completed-fail") return <XCircle className="w-5 h-5 text-destructive" />;
  if (state === "failed-inferred") return <XCircle className="w-5 h-5 text-destructive/50" />;
  if (state === "running") return <Loader2 className="w-5 h-5 text-plum-voltage animate-spin" />;
  if (state === "not-taken") return <CircleSlash className="w-5 h-5 text-white/20" />;
  return null;
}

function StepRow({ step, index, state, result, executionError, isLast, expanded, onToggle }: StepRowProps) {
  const hasOutput = !!(result?.output || result?.error || (state === "failed-inferred" && executionError));
  const isIdle = state === "pending" && !result;
  const isNotTaken = state === "not-taken";

  return (
    <div className="flex gap-3">
      {/* Left rail */}
      <div className="flex flex-col items-center flex-shrink-0 w-5">
        <div className="flex-shrink-0 mt-0.5">
          {isIdle ? (
            <div className="w-5 h-5 rounded-full border border-white/20 flex items-center justify-center">
              <span className="text-[10px] text-smoke">{index + 1}</span>
            </div>
          ) : (
            <StepIcon state={state} />
          )}
        </div>
        {!isLast && (
          <div className={`w-px flex-1 min-h-3 mt-1.5 ${
            state === "completed-ok" ? "bg-success/20" : "bg-white/[0.08]"
          }`} />
        )}
      </div>

      {/* Content */}
      <div className={`flex-1 min-w-0 ${!isLast ? "pb-4" : ""}`}>
        <button
          className={`w-full text-left flex items-start gap-2 group ${hasOutput ? "cursor-pointer" : "cursor-default"}`}
          onClick={() => hasOutput && onToggle()}
          disabled={!hasOutput}
        >
          <p className={`flex-1 text-sm leading-snug ${
            state === "pending" ? "text-white/30"
            : state === "failed-inferred" ? "text-white/50"
            : isNotTaken ? "text-white/30"
            : "text-white"
          }`}>
            {step.task}
            {isNotTaken && (
              <span className="ml-2 text-xs text-white/25 italic">Not taken this run</span>
            )}
          </p>
          {hasOutput && (
            <ChevronDown className={cn(
              "w-3.5 h-3.5 flex-shrink-0 mt-0.5 group-hover:text-white/50",
              motion.colors,
              motion.rotate,
              expanded ? "text-smoke/80 rotate-0" : "text-smoke/80 -rotate-90",
            )} />
          )}
        </button>

        {/* Animated accordion — always rendered, height driven by grid-template-rows */}
        {hasOutput && (
          <div
            className={cn(
              "grid",
              motion.accordion,
              expanded ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0",
            )}
          >
            <div className="overflow-hidden">
              <div className="mt-2 rounded-lg bg-white/[0.03] border border-white/[0.08] px-3 py-2.5 space-y-1.5">
                {result?.output && (
                  <div className="text-xs text-smoke/90 leading-relaxed prose-workflow">
                    <ReactMarkdown
                      components={{
                        h1: ({ children }) => <p className="font-semibold text-white/80 mt-2 mb-0.5">{children}</p>,
                        h2: ({ children }) => <p className="font-semibold text-white/80 mt-2 mb-0.5">{children}</p>,
                        h3: ({ children }) => <p className="font-medium text-white/70 mt-1.5 mb-0.5">{children}</p>,
                        p: ({ children }) => <p className="mb-1.5">{children}</p>,
                        strong: ({ children }) => <strong className="text-white/80 font-medium">{children}</strong>,
                        ul: ({ children }) => <ul className="list-disc pl-4 mb-1.5 space-y-0.5">{children}</ul>,
                        ol: ({ children }) => <ol className="list-decimal pl-4 mb-1.5 space-y-0.5">{children}</ol>,
                        li: ({ children }) => <li>{children}</li>,
                        code: ({ children }) => <code className="bg-white/10 rounded px-1 font-mono">{children}</code>,
                        blockquote: ({ children }) => <blockquote className="border-l-2 border-white/20 pl-2 italic opacity-70">{children}</blockquote>,
                        hr: () => <hr className="border-white/10 my-2" />,
                      }}
                    >
                      {result.output}
                    </ReactMarkdown>
                  </div>
                )}
                {result?.error && (
                  <p className="text-xs text-destructive">{result.error}</p>
                )}
                {state === "failed-inferred" && executionError && !result?.error && (
                  <p className="text-xs text-destructive/70">{executionError}</p>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

interface Props {
  steps: WorkflowStepResponse[];
  execution?: WorkflowExecutionResponse | null;
  isLive?: boolean;
}

export function WorkflowStepsList({ steps, execution, isLive = false }: Props) {
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const hasBranching = steps.some((s) => s.branches.length > 0);

  const rows: Row[] = !execution
    ? steps.map((step, i) => ({ key: `${i}`, step, state: "pending" }))
    : hasBranching
      ? buildBranchingRows(steps, execution)
      : steps.map((step, i) => ({
          key: `${i}`,
          step,
          state: resolveStepState(i, execution.step_results, execution.status),
          result: execution.step_results.find((r) => r.step_index === i),
        }));

  // Reset to collapsed whenever switching to a different execution
  useEffect(() => {
    setExpandedRows(new Set());
  }, [execution?.id]);

  // Auto-expand each row as it completes — only during live runs
  useEffect(() => {
    if (!execution || !isLive) return;
    const nextExpanded = new Set(expandedRows);
    let changed = false;
    for (const row of rows) {
      if (row.result && !nextExpanded.has(row.key)) {
        nextExpanded.add(row.key);
        changed = true;
      }
    }
    if (changed) setExpandedRows(nextExpanded);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [execution?.step_results.length, isLive]);

  if (!steps.length) {
    return <p className="text-sm text-smoke">No steps defined.</p>;
  }

  return (
    <div className="space-y-0">
      {rows.map((row, i) => (
        <StepRow
          key={row.key}
          step={row.step}
          index={i}
          state={row.state}
          result={row.result}
          executionError={execution?.error}
          isLast={i === rows.length - 1}
          expanded={expandedRows.has(row.key)}
          onToggle={() =>
            setExpandedRows((prev) => {
              const next = new Set(prev);
              next.has(row.key) ? next.delete(row.key) : next.add(row.key);
              return next;
            })
          }
        />
      ))}
    </div>
  );
}
