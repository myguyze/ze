import { useQuery } from "@tanstack/react-query";
import { getMessageTrace } from "@ze/client";
import type { MessageTraceResponse } from "@ze/client";
import { queryKeys } from "@/shared/lib";

export function useMessageTraceQuery(messageId: string, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.messageTrace(messageId),
    queryFn: async () => {
      const { data, error } = await getMessageTrace({ path: { message_id: messageId } });
      if (error) return null;
      return data as MessageTraceResponse;
    },
    enabled,
    staleTime: Infinity,
    retry: false,
  });
}
