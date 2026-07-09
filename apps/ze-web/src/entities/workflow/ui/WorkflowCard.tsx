import { useNavigate } from "react-router-dom";
import { Workflow } from "lucide-react";
import type { WorkflowResponse } from "@myguyze/ze-client";
import { Button } from "@/shared/ui";
import { useTriggerWorkflowMutation } from "../api/useTriggerWorkflowMutation";
import { formatSchedule, formatTimestamp } from "../lib/format";

interface WorkflowCardProps {
  workflow: WorkflowResponse;
  variant?: "row" | "grid";
}

function StatusDot({ enabled }: { enabled: boolean }) {
  return (
    <span className="relative flex size-2">
      {enabled && (
        <span className="absolute inline-flex size-full rounded-full bg-plum-voltage opacity-50 animate-ping" />
      )}
      <span
        className={`relative inline-flex size-2 rounded-full ${enabled ? "bg-plum-voltage" : "bg-white/20"}`}
      />
    </span>
  );
}

export function WorkflowCard({ workflow, variant = "row" }: WorkflowCardProps) {
  const trigger = useTriggerWorkflowMutation();
  const navigate = useNavigate();

  if (variant === "grid") {
    return (
      <div
        className="group relative flex flex-col gap-3 p-5 rounded-pill bg-white/[0.02] border border-white/10 hover:bg-white/[0.04] hover:border-white/20 transition-all cursor-pointer overflow-hidden"
        onClick={() => navigate(`/workflows/${workflow.id}`)}
      >
        <div className="absolute inset-0 bg-gradient-to-br from-plum-voltage/[0.06] to-transparent opacity-0 group-hover:opacity-100 transition-opacity rounded-pill" />

        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center justify-center size-9 rounded-full bg-plum-voltage/10 border border-plum-voltage/20 shrink-0">
            <Workflow className="size-4 text-plum-voltage" />
          </div>
          <StatusDot enabled={workflow.enabled} />
        </div>

        <div className="flex-1 min-h-0">
          <p className="text-sm font-medium text-white leading-snug line-clamp-2">{workflow.name}</p>
          {workflow.description && (
            <p className="mt-1 text-xs text-smoke line-clamp-2">{workflow.description}</p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <span
            className={
              workflow.enabled
                ? "inline-block px-2 py-0.5 rounded-full border border-plum-voltage/50 text-plum-voltage text-xs"
                : "inline-block px-2 py-0.5 rounded-full border border-white/20 text-smoke text-xs"
            }
          >
            {workflow.enabled ? "active" : "paused"}
          </span>
          <span className="inline-block px-2 py-0.5 rounded-full border border-white/15 text-smoke text-xs">
            {formatSchedule(workflow.schedule)}
          </span>
        </div>

        {workflow.last_run_at && (
          <p className="text-xs text-smoke/80">Last run {formatTimestamp(workflow.last_run_at)}</p>
        )}

        {workflow.enabled && (
          <Button
            size="sm"
            variant="outline"
            className="w-full mt-auto"
            disabled={trigger.isPending}
            onClick={(e) => { e.stopPropagation(); trigger.mutate(workflow.id); }}
          >
            {trigger.isPending ? "Running…" : "Run now"}
          </Button>
        )}
      </div>
    );
  }

  return (
    <div
      className="group flex items-center gap-4 px-5 py-4 rounded-pill bg-white/[0.02] border border-white/10 hover:bg-white/[0.035] hover:border-white/20 transition-colors cursor-pointer"
      onClick={() => navigate(`/workflows/${workflow.id}`)}
    >
      <div className="flex items-center justify-center size-8 rounded-full bg-plum-voltage/10 border border-plum-voltage/15 shrink-0">
        <Workflow className="size-3.5 text-plum-voltage/80" />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium text-white truncate">{workflow.name}</p>
        </div>
        {workflow.description && (
          <p className="text-xs text-smoke truncate mt-0.5">{workflow.description}</p>
        )}
      </div>

      <div className="hidden md:flex items-center gap-2 shrink-0">
        <span className="inline-block px-2 py-0.5 rounded-full border border-white/15 text-smoke text-xs">
          {formatSchedule(workflow.schedule)}
        </span>
        {(workflow.last_run_at || workflow.next_run_at) && (
          <span className="text-xs text-smoke/80">
            {workflow.last_run_at ? formatTimestamp(workflow.last_run_at) : `Next ${formatTimestamp(workflow.next_run_at!)}`}
          </span>
        )}
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <div className="flex items-center gap-1.5">
          <StatusDot enabled={workflow.enabled} />
          <span
            className={`text-xs ${workflow.enabled ? "text-plum-voltage" : "text-smoke"}`}
          >
            {workflow.enabled ? "active" : "paused"}
          </span>
        </div>
        {workflow.enabled && (
          <Button
            size="sm"
            variant="outline"
            disabled={trigger.isPending}
            onClick={(e) => { e.stopPropagation(); trigger.mutate(workflow.id); }}
          >
            {trigger.isPending ? "Running…" : "Run now"}
          </Button>
        )}
      </div>
    </div>
  );
}
