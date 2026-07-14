import { cancelWorkflowExecution } from "@myguyze/ze-client";
import type { CancelWorkflowExecutionResponse } from "@myguyze/ze-client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/shared/lib";

interface CancelArgs {
  workflowId: string;
  executionId: string;
}

export function useCancelExecutionMutation() {
  const queryClient = useQueryClient();

  return useMutation<CancelWorkflowExecutionResponse, Error, CancelArgs>({
    mutationFn: async ({ workflowId, executionId }: CancelArgs) => {
      const { data, error } = await cancelWorkflowExecution({
        path: { workflow_id: workflowId, execution_id: executionId },
      });
      if (error) throw error;
      return data!;
    },
    onSuccess: (_data, { workflowId }) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.workflowExecutions(workflowId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.workflowDetail(workflowId) });
    },
  });
}
