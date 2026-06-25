import { useMutation, useQueryClient } from "@tanstack/react-query";
import { startGoal } from "@ze/client";
import { queryKeys } from "@/shared/lib";

export function useStartGoalMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (goalId: string) => {
      const { data, error } = await startGoal({ path: { goal_id: goalId } });
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.goals });
    },
  });
}
