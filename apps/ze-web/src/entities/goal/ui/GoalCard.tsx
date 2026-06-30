import { useNavigate } from "react-router-dom";
import type { GoalListItem } from "@myguyze/ze-client";
import { Button } from "@/shared/ui";
import { useStartGoalMutation } from "../api/useStartGoalMutation";

export function GoalCard({ goal }: { goal: GoalListItem }) {
  const navigate = useNavigate();
  const startGoal = useStartGoalMutation();
  const isPlanning = goal.status === "planning";

  return (
    <div
      className="p-4 rounded-pill border border-white/10 hover:border-white/20 transition-colors cursor-pointer"
      onClick={() => navigate(`/goals/${goal.id}`)}
    >
      <p className="text-sm font-medium text-white">{goal.title}</p>
      {goal.objective !== goal.title && (
        <p className="mt-1 text-sm text-smoke">{goal.objective}</p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2" onClick={(e) => e.stopPropagation()}>
        <span className="inline-block px-2 py-0.5 rounded-full border border-plum-voltage/50 text-plum-voltage text-xs">
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
