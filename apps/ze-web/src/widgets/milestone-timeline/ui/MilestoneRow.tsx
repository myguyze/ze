import { useState } from "react";
import type { MilestoneResponse } from "@myguyze/ze-client";
import { CheckCircle2, Circle, Clock, SkipForward, ChevronDown, ChevronUp } from "lucide-react";
import { ExecutionTraceLog } from "./ExecutionTraceLog";

const STATUS_ICON: Record<string, React.ReactNode> = {
  completed: <CheckCircle2 className="w-4 h-4 text-success flex-shrink-0" />,
  in_progress: <Clock className="w-4 h-4 text-plum-voltage flex-shrink-0 animate-pulse" />,
  skipped: <SkipForward className="w-4 h-4 text-smoke/80 flex-shrink-0" />,
  pending: <Circle className="w-4 h-4 text-white/20 flex-shrink-0" />,
};

interface MilestoneRowProps {
  milestone: MilestoneResponse;
  goalId: string;
}

export function MilestoneRow({ milestone, goalId }: MilestoneRowProps) {
  const [expanded, setExpanded] = useState(false);
  const isDone = milestone.status === "completed" || milestone.status === "skipped";

  return (
    <div className="py-3 border-b border-white/5 last:border-0">
      <div className="flex items-start gap-3">
        <div className="mt-0.5">{STATUS_ICON[milestone.status] ?? STATUS_ICON.pending}</div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-white">
            {milestone.sequence}. {milestone.title}
          </p>
          {milestone.output && (
            <p className="mt-0.5 text-xs text-smoke line-clamp-2">{milestone.output}</p>
          )}
          {isDone && (
            <button
              className="mt-1.5 flex items-center gap-1 text-xs text-plum-voltage hover:text-plum-voltage/80 transition-colors"
              onClick={() => setExpanded((v) => !v)}
            >
              {expanded ? (
                <>
                  <ChevronUp className="w-3 h-3" /> Hide tool calls
                </>
              ) : (
                <>
                  <ChevronDown className="w-3 h-3" /> Show tool calls
                </>
              )}
            </button>
          )}
          {expanded && <ExecutionTraceLog goalId={goalId} milestoneId={milestone.id} />}
        </div>
      </div>
    </div>
  );
}
