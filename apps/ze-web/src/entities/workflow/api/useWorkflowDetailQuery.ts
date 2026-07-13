import { getWorkflow } from "@myguyze/ze-client";
import type { WorkflowDetailResponse } from "@myguyze/ze-client";
import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/shared/lib";

export function useWorkflowDetailQuery(workflowId: string) {
  return useQuery<WorkflowDetailResponse>({
    queryKey: queryKeys.workflowDetail(workflowId),
    queryFn: async () => {
      const { data } = await getWorkflow({ path: { workflow_id: workflowId } });
      return data!;
    },
    enabled: !!workflowId,
  });
}
