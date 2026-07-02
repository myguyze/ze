import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Target } from "lucide-react";
import { useGoalDetailQuery } from "@/entities/goal";
import { useSetBreadcrumbTitle } from "@/shared/lib";
import { MilestoneTimeline } from "@/widgets/milestone-timeline";
import { GateStatusCard } from "@/widgets/gate-status";
import { GoalLearningsList } from "@/widgets/goal-learnings";
import { ListSkeleton, ErrorState, PageShell, SectionPanel } from "@/shared/ui";

const ACTIVE_STATUSES = new Set(["active", "planning"]);

function statusBadgeClass(status: string): string {
  if (ACTIVE_STATUSES.has(status)) {
    return "inline-block px-2.5 py-0.5 rounded-full border border-plum-voltage/50 text-plum-voltage text-xs";
  }
  return "inline-block px-2.5 py-0.5 rounded-full border border-white/20 text-smoke text-xs";
}

export function GoalDetailPage() {
  const { goalId } = useParams<{ goalId: string }>();
  const navigate = useNavigate();
  const { data: detail, isLoading, isError, refetch } = useGoalDetailQuery(goalId ?? "");

  useSetBreadcrumbTitle(detail?.title);

  if (isLoading) {
    return (
      <PageShell className="max-w-5xl mx-auto">
        <ListSkeleton count={4} />
      </PageShell>
    );
  }

  if (isError || !detail) {
    return (
      <PageShell className="max-w-5xl mx-auto">
        <ErrorState
          message="Could not load goal."
          onRetry={() => void refetch()}
        />
      </PageShell>
    );
  }

  const activeGates = detail.gates.filter((g) => g.status === "awaiting_approval");

  return (
    <PageShell className="max-w-5xl mx-auto">
      {/* Header */}
      <div>
        <button
          className="flex items-center gap-1.5 text-xs text-smoke hover:text-white transition-colors mb-6"
          onClick={() => navigate("/goals")}
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Goals
        </button>

        <div className="flex items-start gap-4">
          <div className="w-10 h-10 rounded-xl bg-plum-voltage/10 border border-plum-voltage/20 flex items-center justify-center flex-shrink-0 mt-0.5">
            <Target className="w-5 h-5 text-plum-voltage" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-white leading-tight">{detail.title}</h1>
            <p className="text-sm text-smoke/80 mt-2 leading-relaxed max-w-2xl">{detail.objective}</p>
            <div className="flex flex-wrap items-center gap-2 mt-4">
              <span className={statusBadgeClass(detail.status)}>{detail.status}</span>
              {detail.time_horizon && (
                <span className="inline-block px-2.5 py-0.5 rounded-full border border-white/15 text-smoke text-xs">
                  {detail.time_horizon}
                </span>
              )}
              {detail.type && (
                <span className="inline-block px-2.5 py-0.5 rounded-full border border-white/15 text-smoke text-xs">
                  {detail.type}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Main layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <SectionPanel className="lg:col-span-2">
          <h2 className="text-xs font-semibold text-white/40 uppercase tracking-widest mb-5">
            Milestones
          </h2>
          <MilestoneTimeline milestones={detail.milestones} goalId={detail.id} />
        </SectionPanel>

        <SectionPanel>
          <h2 className="text-xs font-semibold text-white/40 uppercase tracking-widest mb-5">
            Learnings
          </h2>
          <GoalLearningsList learnings={detail.learnings} />
          {detail.learnings_summary && !detail.learnings.length && (
            <p className="text-xs text-smoke mt-2">{detail.learnings_summary}</p>
          )}

          {activeGates.length > 0 && (
            <div className="mt-5 pt-5 border-t border-white/[0.06]">
              <h2 className="text-xs font-semibold text-white/40 uppercase tracking-widest mb-5">
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
            <div className="mt-5 pt-5 border-t border-white/[0.06]">
              <h2 className="text-xs font-semibold text-white/40 uppercase tracking-widest mb-5">
                Retrospective
              </h2>
              <p className="text-xs text-smoke leading-relaxed">{detail.retrospective_text}</p>
            </div>
          )}
        </SectionPanel>
      </div>
    </PageShell>
  );
}
