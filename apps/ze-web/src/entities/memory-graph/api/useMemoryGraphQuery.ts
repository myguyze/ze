import { useQuery } from "@tanstack/react-query";
import { getMemoryGraph } from "@ze/client";
import type { MemoryGraphResponse } from "@ze/client";
import { queryKeys } from "@/shared/lib";

export interface MemoryGraphFilters {
  entityType?: string;
  seedId?: string;
  limit?: number;
}

export function useMemoryGraphQuery(filters: MemoryGraphFilters = {}) {
  return useQuery({
    queryKey: queryKeys.memoryGraph(filters.entityType, filters.seedId),
    queryFn: async () => {
      const { data } = await getMemoryGraph({
        query: {
          limit: filters.limit ?? 50,
          entity_type: filters.entityType ?? undefined,
          seed_id: filters.seedId ?? undefined,
        },
      });
      return data as MemoryGraphResponse;
    },
  });
}
