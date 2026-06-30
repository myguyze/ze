import { useQuery } from "@tanstack/react-query";
import { listWorkflows } from "@myguyze/ze-client";
import type { WorkflowResponse } from "@myguyze/ze-client";
import { queryKeys } from "@/shared/lib";

export function useWorkflowsQuery() {
  return useQuery<WorkflowResponse[]>({
    queryKey: queryKeys.workflows,
    queryFn: async () => {
      const { data } = await listWorkflows();
      return data ?? [];
    },
  });
}
