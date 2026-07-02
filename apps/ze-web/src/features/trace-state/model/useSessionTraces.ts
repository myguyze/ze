import type { WsTraceUpdateFrame } from "@myguyze/ze-client";
import { getMessageTrace } from "@myguyze/ze-client";
import { useQueries, useQueryClient } from "@tanstack/react-query";
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

  const traceQueries = useQueries({
    queries: assistantMessageIds.map((messageId) => ({
      queryKey: queryKeys.messageTrace(messageId),
      queryFn: async () => {
        const { data, error } = await getMessageTrace({ path: { message_id: messageId } });
        if (error || !data) return null;
        return toTraceFrame(messageId, data);
      },
      staleTime: Infinity,
      retry: false,
    })),
  });

  const isLoading = assistantMessageIds.length > 0 && traceQueries.some((q) => q.isLoading);

  const queryStatusKey = traceQueries
    .map((q, i) => {
      const id = assistantMessageIds[i] ?? "";
      if (q.isLoading || q.isFetching) return `${id}:pending`;
      if (q.data) return `${id}:hit`;
      return `${id}:miss`;
    })
    .join("|");

  useEffect(() => {
    if (idsKey.length === 0) {
      setHydrating(false);
      return;
    }

    setHydrating(isLoading);
    if (isLoading) return;

    const messageIds = idsKey.split(",");
    const incoming = messageIds
      .map((id) =>
        queryClient.getQueryData<WsTraceUpdateFrame | null>(queryKeys.messageTrace(id)),
      )
      .filter((t): t is WsTraceUpdateFrame => t !== null && t !== undefined);

    mergeTraces(incoming, messageIds);
  }, [threadId, idsKey, queryStatusKey, isLoading, mergeTraces, setHydrating, queryClient]);

  return hydrating;
}
