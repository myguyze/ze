import { useQuery } from "@tanstack/react-query";
import { getMemoryActivity } from "@myguyze/ze-client";
import type { MemoryActivityResponse } from "@myguyze/ze-client";

export function useMemoryActivityQuery(start: Date | undefined, end: Date | undefined) {
  return useQuery({
    queryKey: ["memory-activity", start?.toISOString(), end?.toISOString()],
    queryFn: async () => {
      const { data } = await getMemoryActivity({
        query: { start: start!.toISOString(), end: end!.toISOString() },
      });
      return data as MemoryActivityResponse;
    },
    enabled: Boolean(start && end),
    staleTime: 60_000,
  });
}
