import { useInfiniteQuery } from "@tanstack/react-query";
import { getMemoryFeed } from "@ze/client";
import type { MemoryFeedResponse } from "@ze/client";
import { queryKeys } from "@/shared/lib";

export interface MemoryFeedFilters {
  type: "all" | "fact" | "episode";
  agent?: string;
}

export function useMemoryFeedQuery(filters: MemoryFeedFilters, asOf?: string) {
  return useInfiniteQuery({
    queryKey: queryKeys.memoryFeed(filters.type, filters.agent, asOf),
    queryFn: async ({ pageParam }) => {
      const { data } = await getMemoryFeed({
        query: {
          limit: 50,
          before: pageParam ?? undefined,
          type: filters.type,
          agent: filters.agent ?? undefined,
          as_of: asOf ?? undefined,
        },
      });
      return data as MemoryFeedResponse;
    },
    getNextPageParam: (lastPage) => lastPage?.next_before ?? undefined,
    initialPageParam: undefined as string | undefined,
  });
}
