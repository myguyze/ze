import { useNavigate } from "react-router-dom";
import { Target } from "lucide-react";
import type { GoalListItem } from "@myguyze/ze-client";
import { Button } from "@/shared/ui";
import { useStartGoalMutation } from "../api/useStartGoalMutation";

interface GoalCardProps {
  goal: GoalListItem;
  variant?: "row" | "grid";
}

function statusStyle(status: string) {
  if (status === "active") return "border-plum-voltage/50 text-plum-voltage";
  if (status === "completed") return "border-success/50 text-success";
  if (status === "abandoned") return "border-white/20 text-smoke";
  return "border-white/20 text-smoke";
}

export function GoalCard({ goal, variant = "row" }: GoalCardProps) {
  const navigate = useNavigate();
  const startGoal = useStartGoalMutation();
  const isPlanning = goal.status === "planning";

  if (variant === "grid") {
    return (
      <div
        className="group relative flex flex-col gap-3 p-5 rounded-pill bg-white/[0.02] border border-white/10 hover:bg-white/[0.04] hover:border-white/20 transition-all cursor-pointer overflow-hidden"
        onClick={() => navigate(`/goals/${goal.id}`)}
      >
        <div className="absolute inset-0 bg-gradient-to-br from-plum-voltage/[0.06] to-transparent opacity-0 group-hover:opacity-100 transition-opacity rounded-pill" />

        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center justify-center size-9 rounded-full bg-plum-voltage/10 border border-plum-voltage/20 shrink-0">
            <Target className="size-4 text-plum-voltage" />
          </div>
        </div>

        <div className="flex-1 min-h-0">
          <p className="text-sm font-medium text-white leading-snug line-clamp-2">{goal.title}</p>
          {goal.objective !== goal.title && (
            <p className="mt-1 text-xs text-smoke line-clamp-2">{goal.objective}</p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
          <span className={`inline-block px-2 py-0.5 rounded-full border text-xs ${statusStyle(goal.status)}`}>
            {goal.status}
          </span>
          {isPlanning && (
            <Button
              size="sm"
              variant="outline"
              className="mt-auto"
              disabled={startGoal.isPending}
              onClick={() => startGoal.mutate(goal.id)}
            >
              {startGoal.isPending ? "Starting…" : "Start goal"}
            </Button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div
      className="group flex items-center gap-4 px-5 py-4 rounded-pill bg-white/[0.02] border border-white/10 hover:bg-white/[0.035] hover:border-white/20 transition-colors cursor-pointer"
      onClick={() => navigate(`/goals/${goal.id}`)}
    >
      <div className="flex items-center justify-center size-8 rounded-full bg-plum-voltage/10 border border-plum-voltage/15 shrink-0">
        <Target className="size-3.5 text-plum-voltage/80" />
      </div>

      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-white truncate">{goal.title}</p>
        {goal.objective !== goal.title && (
          <p className="text-xs text-smoke truncate mt-0.5">{goal.objective}</p>
        )}
      </div>

      <div className="flex items-center gap-2 shrink-0" onClick={(e) => e.stopPropagation()}>
        <span className={`inline-block px-2 py-0.5 rounded-full border text-xs ${statusStyle(goal.status)}`}>
          {goal.status}
        </span>
        {isPlanning && (
          <Button
            size="sm"
            variant="outline"
            disabled={startGoal.isPending}
            onClick={() => startGoal.mutate(goal.id)}
          >
            {startGoal.isPending ? "Starting…" : "Start goal"}
          </Button>
        )}
      </div>
    </div>
  );
}
