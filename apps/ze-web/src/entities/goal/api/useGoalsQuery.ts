import { useQuery } from "@tanstack/react-query";
import { listGoals } from "@myguyze/ze-client";
import type { GoalListItem } from "@myguyze/ze-client";
import { queryKeys } from "@/shared/lib";

export function useGoalsQuery() {
  return useQuery<GoalListItem[]>({
    queryKey: queryKeys.goals,
    queryFn: async () => {
      const { data } = await listGoals();
      return data ?? [];
    },
  });
}
