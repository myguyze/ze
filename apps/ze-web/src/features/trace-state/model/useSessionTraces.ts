import type { WsTraceUpdateFrame } from "@myguyze/ze-client";
import { getMessageTraces } from "@myguyze/ze-client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { queryKeys } from "@/shared/lib";
import { toTraceFrame } from "../lib/toTraceFrame";
import { useTraceStore } from "./useTraceStore";

export function useSessionTraces(threadId: string, assistantMessageIds: string[]) {
  const queryClient = useQueryClient();
  const clearTraces = useTraceStore((s) => s.clearTraces);
  const mergeTraces = useTraceStore((s) => s.mergeTraces);
  const setHydrating = useTraceStore((s) => s.setHydrating);
  const hydrating = useTraceStore((s) => s.hydrating);

  const idsKey = assistantMessageIds.join(",");

  useEffect(() => {
    clearTraces();
  }, [threadId, clearTraces]);

  const { data: traceFrames, isLoading } = useQuery({
    queryKey: queryKeys.messageTraces(threadId, idsKey),
    queryFn: async () => {
      if (assistantMessageIds.length === 0) return [] as WsTraceUpdateFrame[];
      const { data, error } = await getMessageTraces({
        query: { ids: assistantMessageIds },
      });
      if (error || !data) return [];
      const byId = new Map(
        data.traces.map((entry) => [
          entry.message_id,
          toTraceFrame(entry.message_id, entry.trace),
        ]),
      );
      return assistantMessageIds
        .map((id) => byId.get(id))
        .filter((frame): frame is WsTraceUpdateFrame => frame !== undefined);
    },
    enabled: assistantMessageIds.length > 0,
    staleTime: Infinity,
    retry: false,
  });

  useEffect(() => {
    if (idsKey.length === 0) {
      setHydrating(false);
      return;
    }

    setHydrating(isLoading);
    if (isLoading) return;

    const messageIds = idsKey.split(",");
    mergeTraces(traceFrames ?? [], messageIds);
    for (const frame of traceFrames ?? []) {
      queryClient.setQueryData(queryKeys.messageTrace(frame.message_id), frame);
    }
  }, [threadId, idsKey, isLoading, traceFrames, mergeTraces, setHydrating, queryClient]);

  return hydrating;
}
