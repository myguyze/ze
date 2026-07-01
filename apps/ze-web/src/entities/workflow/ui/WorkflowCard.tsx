import { useNavigate } from "react-router-dom";
import type { WorkflowResponse } from "@myguyze/ze-client";
import { Button } from "@/shared/ui";
import { useTriggerWorkflowMutation } from "../api/useTriggerWorkflowMutation";
import { formatSchedule, formatTimestamp } from "../lib/format";

export function WorkflowCard({ workflow }: { workflow: WorkflowResponse }) {
  const trigger = useTriggerWorkflowMutation();
  const navigate = useNavigate();

  return (
    <div
      className="p-5 rounded-pill bg-white/[0.02] border border-white/10 hover:bg-white/[0.035] hover:border-white/20 transition-colors cursor-pointer"
      onClick={() => navigate(`/workflows/${workflow.id}`)}
    >
      <p className="text-sm font-medium text-white">{workflow.name}</p>
      {workflow.description && (
        <p className="mt-1 text-sm text-smoke">{workflow.description}</p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
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
      {(workflow.last_run_at || workflow.next_run_at) && (
        <p className="mt-2 text-xs text-smoke">
          {workflow.last_run_at && <>Last run {formatTimestamp(workflow.last_run_at)}</>}
          {workflow.last_run_at && workflow.next_run_at && " · "}
          {workflow.next_run_at && <>Next {formatTimestamp(workflow.next_run_at)}</>}
        </p>
      )}
    </div>
  );
}
