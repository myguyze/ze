import { triggerWorkflow } from "@myguyze/ze-client";
import type { TriggerWorkflowResponse } from "@myguyze/ze-client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/shared/lib";

export function useTriggerWorkflowMutation() {
  const queryClient = useQueryClient();

  return useMutation<TriggerWorkflowResponse, Error, string>({
    mutationFn: async (workflowId: string) => {
      const { data, error } = await triggerWorkflow({ path: { workflow_id: workflowId } });
      if (error) throw error;
      return data!;
    },
    onSuccess: (_data, workflowId) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.workflows });
      void queryClient.invalidateQueries({ queryKey: queryKeys.workflowExecutions(workflowId) });
    },
  });
}
