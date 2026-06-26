import { useMutation, useQueryClient } from "@tanstack/react-query";
import { triggerWorkflow } from "@ze/client";
import { queryKeys } from "@/shared/lib";

export function useTriggerWorkflowMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (workflowId: string) => {
      const { data, error } = await triggerWorkflow({ path: { workflow_id: workflowId } });
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.workflows });
    },
  });
}
