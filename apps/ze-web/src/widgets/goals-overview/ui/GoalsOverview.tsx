import { Target } from "lucide-react";
import { FloatingButton } from "@/features/open-context-overlay";
import { GoalCard, useGoalsQuery } from "@/entities/goal";
import { ListPage } from "@/shared/ui";

export function GoalsOverview() {
  const { data: goals, isLoading, isError, refetch } = useGoalsQuery();

  return (
    <>
      <ListPage
        isLoading={isLoading}
        isError={isError}
        isEmpty={!goals?.length}
        emptyIcon={Target}
        emptyMessage="No goals yet. Ask Ze to set one."
        errorMessage="Could not load goals."
        onRetry={() => void refetch()}
      >
        <div className="space-y-3">
          {goals?.map((goal) => (
            <GoalCard key={goal.id} goal={goal} />
          ))}
        </div>
      </ListPage>

      <FloatingButton screen="goals" />
    </>
  );
}
