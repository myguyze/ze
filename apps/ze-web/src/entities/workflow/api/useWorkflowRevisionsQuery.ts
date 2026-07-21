import { listWorkflowRevisions } from "@myguyze/ze-client";
import type { WorkflowRevisionResponse } from "@myguyze/ze-client";
import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/shared/lib";

export function useWorkflowRevisionsQuery(workflowId: string) {
  return useQuery<WorkflowRevisionResponse[]>({
    queryKey: queryKeys.workflowRevisions(workflowId),
    queryFn: async () => {
      const { data } = await listWorkflowRevisions({ path: { workflow_id: workflowId } });
      return data ?? [];
    },
    enabled: !!workflowId,
  });
}
