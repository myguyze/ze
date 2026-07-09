import { useGoalTracesQuery } from "@/entities/goal";
import { TraceRow } from "./TraceRow";

interface ExecutionTraceLogProps {
  goalId: string;
  milestoneId: string;
}

export function ExecutionTraceLog({ goalId, milestoneId }: ExecutionTraceLogProps) {
  const { data: traces, isLoading } = useGoalTracesQuery(goalId, milestoneId);

  if (isLoading) {
    return <p className="text-xs text-smoke/80 py-2">Loading traces…</p>;
  }

  if (!traces?.length) {
    return <p className="text-xs text-smoke/80 italic py-2">No tool calls recorded.</p>;
  }

  return (
    <div className="mt-2 pl-3 border-l border-white/10">
      {traces.map((trace) => (
        <TraceRow key={trace.id} trace={trace} />
      ))}
    </div>
  );
}
