import type { MilestoneResponse } from "@ze/client";
import { MilestoneRow } from "./MilestoneRow";

interface MilestoneTimelineProps {
  milestones: MilestoneResponse[];
  goalId: string;
}

export function MilestoneTimeline({ milestones, goalId }: MilestoneTimelineProps) {
  if (!milestones.length) {
    return <p className="text-sm text-smoke/60 italic">No milestones planned yet.</p>;
  }

  return (
    <div>
      {milestones.map((m) => (
        <MilestoneRow key={m.id} milestone={m} goalId={goalId} />
      ))}
    </div>
  );
}
