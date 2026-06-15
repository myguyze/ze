import { useQuery } from "@tanstack/react-query";
import { Target } from "lucide-react";
import { api } from "@/lib/api";
import { type Goal } from "@/types/api";
import { FloatingButton } from "@/features/overlay/FloatingButton";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/layout/EmptyState";
import { ListSkeleton } from "@/components/layout/ListSkeleton";

export function GoalsPage() {
  const { data: goals, isLoading } = useQuery({
    queryKey: ["goals"],
    queryFn: () => api.get<Goal[]>("/api/goals"),
  });

  return (
    <div className="px-4 py-8 space-y-6">
      <PageHeader label="Goals" title="Active goals" />

      {isLoading && <ListSkeleton />}

      {goals?.length === 0 && (
        <EmptyState icon={Target} message="No active goals. Ask Ze to set one." />
      )}

      {goals && goals.length > 0 && (
        <div className="space-y-3">
          {goals.map((goal) => (
            <div
              key={goal.id}
              className="p-4 rounded-[24px] border border-white/10 hover:border-white/20 transition-colors cursor-pointer"
            >
              <p className="text-sm text-white">{goal.objective}</p>
              <span className="mt-2 inline-block px-2 py-0.5 rounded-full border border-[#8052ff]/50 text-[#8052ff] text-xs">
                {goal.status}
              </span>
            </div>
          ))}
        </div>
      )}

      <FloatingButton screen="goals" />
    </div>
  );
}
