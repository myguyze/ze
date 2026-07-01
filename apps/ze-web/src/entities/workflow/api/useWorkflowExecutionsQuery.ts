import { useQuery } from "@tanstack/react-query";
import { listWorkflowExecutions } from "@myguyze/ze-client";
import type { WorkflowExecutionResponse } from "@myguyze/ze-client";
import { queryKeys } from "@/shared/lib";

export function useWorkflowExecutionsQuery(workflowId: string) {
  return useQuery<WorkflowExecutionResponse[]>({
    queryKey: queryKeys.workflowExecutions(workflowId),
    queryFn: async () => {
      const { data } = await listWorkflowExecutions({ path: { workflow_id: workflowId } });
      return data ?? [];
    },
    enabled: !!workflowId,
  });
}
