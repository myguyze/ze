import { listWorkflowExecutions } from "@myguyze/ze-client";
import type { WorkflowExecutionResponse } from "@myguyze/ze-client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/shared/lib";

const POLL_INTERVAL_MS = 2000;

function isDone(ex: WorkflowExecutionResponse): boolean {
  if (ex.status === "running") return false;
  // Keep polling until the DB writes (step_results + error) have caught up
  if (ex.step_results.length === 0 && !ex.error && !ex.summary) return false;
  return true;
}

export function useLiveExecutionQuery(workflowId: string, executionId: string | null) {
  const queryClient = useQueryClient();

  return useQuery<WorkflowExecutionResponse | null>({
    queryKey: [...queryKeys.workflowExecutions(workflowId), "live", executionId],
    queryFn: async () => {
      if (!executionId) return null;
      const { data } = await listWorkflowExecutions({ path: { workflow_id: workflowId } });
      const execution = (data ?? []).find((ex) => ex.id === executionId) ?? null;

      if (execution && isDone(execution)) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.workflowExecutions(workflowId) });
      }

      return execution;
    },
    enabled: !!workflowId && !!executionId,
    refetchInterval: (query) => {
      const ex = query.state.data;
      if (!ex || !isDone(ex)) return POLL_INTERVAL_MS;
      return false;
    },
  });
}
