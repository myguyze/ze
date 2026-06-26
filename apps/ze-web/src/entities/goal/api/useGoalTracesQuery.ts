import { useQuery } from "@tanstack/react-query";
import { listGoalTraces } from "@ze/client";
import type { ExecutionTraceResponse } from "@ze/client";
import { queryKeys } from "@/shared/lib";

export function useGoalTracesQuery(goalId: string, milestoneId?: string) {
  return useQuery<ExecutionTraceResponse[]>({
    queryKey: queryKeys.goalTraces(goalId, milestoneId),
    queryFn: async () => {
      const { data, error } = await listGoalTraces({
        path: { goal_id: goalId },
        query: milestoneId ? { milestone_id: milestoneId } : undefined,
      });
      if (error) throw error;
      return data ?? [];
    },
    enabled: !!goalId && !!milestoneId,
  });
}
