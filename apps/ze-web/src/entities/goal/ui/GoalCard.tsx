import type { GoalListItem } from "@ze/client";

export function GoalCard({ goal }: { goal: GoalListItem }) {
  return (
    <div className="p-4 rounded-pill border border-white/10 hover:border-white/20 transition-colors cursor-pointer">
      <p className="text-sm text-white">{goal.objective}</p>
      <span className="mt-2 inline-block px-2 py-0.5 rounded-full border border-plum-voltage/50 text-plum-voltage text-xs">
        {goal.status}
      </span>
    </div>
  );
}
