import { Info, AlertTriangle } from "lucide-react";

export type WorkflowDefinitionNoticeMode =
  | "current"
  | "historical"
  | "historical-edited-since"
  | "legacy-unavailable";

interface WorkflowDefinitionNoticeProps {
  mode: WorkflowDefinitionNoticeMode;
  startedAt?: string | null;
}

function formatStartedAt(iso: string | null | undefined): string {
  if (!iso) return "this run";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function noticeCopy(mode: WorkflowDefinitionNoticeMode, startedAt?: string | null): string {
  const when = formatStartedAt(startedAt);
  switch (mode) {
    case "current":
      return "Current definition";
    case "historical":
      return `Showing definition from this run (${when})`;
    case "historical-edited-since":
      return `This run used the workflow as it was on ${when}. The definition has changed since then.`;
    case "legacy-unavailable":
      return "Definition at run time is unavailable. The graph may not match what actually ran.";
    default: {
      const _exhaustive: never = mode;
      return _exhaustive;
    }
  }
}

export function WorkflowDefinitionNotice({ mode, startedAt }: WorkflowDefinitionNoticeProps) {
  const isWarning = mode === "historical-edited-since" || mode === "legacy-unavailable";
  const Icon = isWarning ? AlertTriangle : Info;

  return (
    <div
      className={
        isWarning
          ? "mb-4 flex items-start gap-2 rounded-xl border border-amber-spark/30 bg-amber-spark/[0.06] px-3 py-2.5 text-xs text-amber-spark"
          : "mb-4 flex items-start gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2.5 text-xs text-smoke"
      }
      role="status"
    >
      <Icon className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
      <p>{noticeCopy(mode, startedAt)}</p>
    </div>
  );
}
