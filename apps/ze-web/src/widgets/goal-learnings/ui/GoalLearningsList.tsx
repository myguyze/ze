import type { LearningResponse } from "@myguyze/ze-client";

interface GoalLearningsListProps {
  learnings: LearningResponse[];
}

export function GoalLearningsList({ learnings }: GoalLearningsListProps) {
  if (!learnings.length) {
    return <p className="text-xs text-smoke/80 italic">No learnings yet.</p>;
  }

  return (
    <ul className="space-y-2">
      {learnings.map((l) => (
        <li key={l.id} className="flex items-start gap-2 text-xs text-smoke">
          <span className="mt-0.5 text-plum-voltage flex-shrink-0">•</span>
          <span>{l.content}</span>
        </li>
      ))}
    </ul>
  );
}
