import { useQuery } from "@tanstack/react-query";
import { getEntityDetail } from "@ze/client";
import type { EntityDetailResponse } from "@ze/client";
import { queryKeys } from "@/shared/lib";

export function useEntityDetailQuery(entityId: string | null) {
  return useQuery({
    queryKey: queryKeys.entityDetail(entityId ?? ""),
    queryFn: async () => {
      const { data } = await getEntityDetail({ path: { entity_id: entityId! } });
      return data as EntityDetailResponse;
    },
    enabled: entityId !== null,
  });
}
