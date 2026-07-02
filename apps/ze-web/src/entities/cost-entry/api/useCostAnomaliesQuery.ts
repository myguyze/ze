import { useQuery } from "@tanstack/react-query";
import { getCostAnomalies } from "@myguyze/ze-client";
import type { CostAnomaliesResponse } from "@myguyze/ze-client";
import { queryKeys } from "@/shared/lib";

export function useCostAnomaliesQuery() {
  return useQuery<CostAnomaliesResponse>({
    queryKey: queryKeys.costAnomalies,
    queryFn: async () => {
      const { data } = await getCostAnomalies();
      return data!;
    },
  });
}
