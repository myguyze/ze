import { X, CheckCircle2, XCircle, Loader2, CircleSlash, Circle } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { formatDurationMs, type WorkflowGraphNode, type StepState } from "@/entities/workflow";

const STATE_ICON: Record<StepState, React.ComponentType<{ className?: string }>> = {
  "completed-ok": CheckCircle2,
  "completed-fail": XCircle,
  "failed-inferred": XCircle,
  running: Loader2,
  pending: Circle,
  "not-taken": CircleSlash,
};

const STATE_LABEL: Record<StepState, string> = {
  "completed-ok": "Completed",
  "completed-fail": "Failed",
  "failed-inferred": "Failed",
  running: "Running",
  pending: "Pending",
  "not-taken": "Not taken this run",
};

const markdownComponents = {
  h1: ({ children }: { children?: React.ReactNode }) => <p className="font-semibold text-white/80 mt-2 mb-0.5">{children}</p>,
  h2: ({ children }: { children?: React.ReactNode }) => <p className="font-semibold text-white/80 mt-2 mb-0.5">{children}</p>,
  h3: ({ children }: { children?: React.ReactNode }) => <p className="font-medium text-white/70 mt-1.5 mb-0.5">{children}</p>,
  p: ({ children }: { children?: React.ReactNode }) => <p className="mb-1.5">{children}</p>,
  strong: ({ children }: { children?: React.ReactNode }) => <strong className="text-white/80 font-medium">{children}</strong>,
  ul: ({ children }: { children?: React.ReactNode }) => <ul className="list-disc pl-4 mb-1.5 space-y-0.5">{children}</ul>,
  ol: ({ children }: { children?: React.ReactNode }) => <ol className="list-decimal pl-4 mb-1.5 space-y-0.5">{children}</ol>,
  li: ({ children }: { children?: React.ReactNode }) => <li>{children}</li>,
  code: ({ children }: { children?: React.ReactNode }) => <code className="bg-white/10 rounded px-1 font-mono">{children}</code>,
  blockquote: ({ children }: { children?: React.ReactNode }) => (
    <blockquote className="border-l-2 border-white/20 pl-2 italic opacity-70">{children}</blockquote>
  ),
  hr: () => <hr className="border-white/10 my-2" />,
};

interface Props {
  node: WorkflowGraphNode;
  executionError: string | null;
  onClose: () => void;
}

export function StepDetailPanel({ node, executionError, onClose }: Props) {
  const { step, state, result } = node;
  const Icon = STATE_ICON[state];
  const showInferredError = state === "failed-inferred" && executionError && !result?.error;

  return (
    <div className="flex flex-col h-full bg-white/[0.03] border-l border-white/10 overflow-hidden">
      <div className="flex items-start justify-between p-4 border-b border-white/10 flex-shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <Icon
            className={`w-4 h-4 shrink-0 ${
              state === "completed-ok"
                ? "text-success"
                : state === "completed-fail" || state === "failed-inferred"
                  ? "text-destructive"
                  : state === "running"
                    ? "text-plum-voltage animate-spin"
                    : "text-smoke"
            }`}
          />
          <div className="min-w-0">
            <p className="text-sm font-medium text-white leading-tight line-clamp-2">{step.task}</p>
            <p className="text-xs text-smoke">
              {STATE_LABEL[state]}
              {result && ` • ${formatDurationMs(result.duration_ms)}`}
              {result?.attempt_count != null && result.attempt_count > 1 && ` • ${result.attempt_count} attempts`}
              {result?.no_results && " • No new results"}
            </p>
          </div>
        </div>
        <button onClick={onClose} className="text-smoke hover:text-white transition-colors shrink-0">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {step.agent_hint && (
          <section>
            <p className="text-xs font-medium text-smoke uppercase tracking-wider mb-1">Agent</p>
            <p className="text-xs text-white/80">{step.agent_hint}</p>
          </section>
        )}

        {step.verify && (
          <section>
            <p className="text-xs font-medium text-smoke uppercase tracking-wider mb-1">Verify</p>
            <p className="text-xs text-white/70 font-mono">{step.verify}</p>
          </section>
        )}

        {result?.output && (
          <section>
            <p className="text-xs font-medium text-smoke uppercase tracking-wider mb-2">Output</p>
            <div className="text-xs text-smoke/90 leading-relaxed prose-workflow">
              <ReactMarkdown components={markdownComponents}>{result.output}</ReactMarkdown>
            </div>
          </section>
        )}

        {result?.error && (
          <section>
            <p className="text-xs font-medium text-smoke uppercase tracking-wider mb-1">Error</p>
            <p className="text-xs text-destructive">{result.error}</p>
          </section>
        )}

        {showInferredError && (
          <section>
            <p className="text-xs font-medium text-smoke uppercase tracking-wider mb-1">Error</p>
            <p className="text-xs text-destructive/70">{executionError}</p>
          </section>
        )}

        {!step.agent_hint && !step.verify && !result?.output && !result?.error && !showInferredError && (
          <p className="text-xs text-smoke text-center py-4">No details for this step yet.</p>
        )}
      </div>
    </div>
  );
}
