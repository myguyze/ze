import { useQuery } from "@tanstack/react-query";
import { getGoalDetail } from "@myguyze/ze-client";
import type { GoalDetailResponse } from "@myguyze/ze-client";
import { queryKeys } from "@/shared/lib";

export function useGoalDetailQuery(goalId: string) {
  return useQuery<GoalDetailResponse>({
    queryKey: queryKeys.goalDetail(goalId),
    queryFn: async () => {
      const { data, error } = await getGoalDetail({ path: { goal_id: goalId } });
      if (error) throw error;
      return data!;
    },
    enabled: !!goalId,
  });
}
