import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Target } from "lucide-react";
import { useGoalDetailQuery } from "@/entities/goal";
import { MilestoneTimeline } from "@/widgets/milestone-timeline";
import { GateStatusCard } from "@/widgets/gate-status";
import { GoalLearningsList } from "@/widgets/goal-learnings";
import { ListSkeleton, ErrorState } from "@/shared/ui";

export function GoalDetailPage() {
  const { goalId } = useParams<{ goalId: string }>();
  const navigate = useNavigate();
  const { data: detail, isLoading, isError, refetch } = useGoalDetailQuery(goalId ?? "");

  if (isLoading) {
    return (
      <div className="px-4 py-8">
        <ListSkeleton count={4} />
      </div>
    );
  }

  if (isError || !detail) {
    return (
      <div className="px-4 py-8">
        <ErrorState
          message="Could not load goal."
          onRetry={() => void refetch()}
        />
      </div>
    );
  }

  const activeGates = detail.gates.filter((g) => g.status === "awaiting_approval");

  return (
    <div className="px-4 py-6 space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div>
        <button
          className="flex items-center gap-1.5 text-xs text-smoke hover:text-white transition-colors mb-4"
          onClick={() => navigate("/goals")}
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Goals
        </button>

        <div className="flex items-start gap-3">
          <Target className="w-5 h-5 text-plum-voltage flex-shrink-0 mt-0.5" />
          <div>
            <h1 className="text-lg font-semibold text-white">{detail.title}</h1>
            <p className="text-sm text-smoke mt-0.5">{detail.objective}</p>
            <span className="inline-block mt-2 px-2 py-0.5 rounded-full border border-plum-voltage/50 text-plum-voltage text-xs">
              {detail.status}
            </span>
          </div>
        </div>
      </div>

      {/* Main layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Milestone timeline — 2/3 width on large screens */}
        <div className="lg:col-span-2">
          <h2 className="text-sm font-medium text-white/70 uppercase tracking-wide mb-3">
            Milestones
          </h2>
          <MilestoneTimeline milestones={detail.milestones} goalId={detail.id} />
        </div>

        {/* Sidebar — learnings + active gates */}
        <div className="space-y-6">
          <div>
            <h2 className="text-sm font-medium text-white/70 uppercase tracking-wide mb-3">
              Learnings
            </h2>
            <GoalLearningsList learnings={detail.learnings} />
            {detail.learnings_summary && !detail.learnings.length && (
              <p className="text-xs text-smoke">{detail.learnings_summary}</p>
            )}
          </div>

          {activeGates.length > 0 && (
            <div>
              <h2 className="text-sm font-medium text-white/70 uppercase tracking-wide mb-3">
                Gate
              </h2>
              <div className="space-y-3">
                {activeGates.map((gate) => (
                  <GateStatusCard key={gate.id} gate={gate} goalId={detail.id} />
                ))}
              </div>
            </div>
          )}

          {detail.retrospective_text && (
            <div>
              <h2 className="text-sm font-medium text-white/70 uppercase tracking-wide mb-3">
                Retrospective
              </h2>
              <p className="text-xs text-smoke">{detail.retrospective_text}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
