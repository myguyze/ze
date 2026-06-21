import { useQuery } from "@tanstack/react-query";
import { Target } from "lucide-react";
import { listGoals } from "@ze/client";
import type { GoalListItem } from "@ze/client";
import { queryKeys } from "@/lib/queryKeys";
import { FloatingButton } from "@/features/overlay/FloatingButton";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/layout/EmptyState";
import { ErrorState } from "@/components/layout/ErrorState";
import { ListSkeleton } from "@/components/layout/ListSkeleton";

export function GoalsPage() {
  const { data: goals, isLoading, isError, refetch } = useQuery<GoalListItem[]>({
    queryKey: queryKeys.goals,
    queryFn: async () => {
      const { data } = await listGoals();
      return data ?? [];
    },
  });

  return (
    <div className="px-4 py-8 space-y-6">
      <PageHeader label="Goals" title="Active goals" />

      {isLoading && <ListSkeleton />}

      {isError && (
        <ErrorState
          message="Could not load goals."
          onRetry={() => void refetch()}
        />
      )}

      {!isError && goals?.length === 0 && (
        <EmptyState icon={Target} message="No active goals. Ask Ze to set one." />
      )}

      {!isError && goals && goals.length > 0 && (
        <div className="space-y-3">
          {goals.map((goal) => (
            <div
              key={goal.id}
              className="p-4 rounded-pill border border-white/10 hover:border-white/20 transition-colors cursor-pointer"
            >
              <p className="text-sm text-white">{goal.objective}</p>
              <span className="mt-2 inline-block px-2 py-0.5 rounded-full border border-plum-voltage/50 text-plum-voltage text-xs">
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
