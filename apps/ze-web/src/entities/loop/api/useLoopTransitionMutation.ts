import { confirmLoop, closeLoop, dropLoop } from "@myguyze/ze-client";
import type { LoopTransitionResponse } from "@myguyze/ze-client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/shared/lib";

export type LoopTransitionKind = "confirm" | "close" | "drop";

const TRANSITION_FN = {
  confirm: confirmLoop,
  close: closeLoop,
  drop: dropLoop,
} as const;

export function useLoopTransitionMutation() {
  const queryClient = useQueryClient();

  return useMutation<
    LoopTransitionResponse,
    Error,
    { loopId: string; kind: LoopTransitionKind }
  >({
    mutationFn: async ({ loopId, kind }) => {
      const { data, error } = await TRANSITION_FN[kind]({ path: { loop_id: loopId } });
      if (error) throw error;
      return data!;
    },
    onSuccess: (_data, { loopId }) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.loops() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.loopDetail(loopId) });
    },
  });
}
