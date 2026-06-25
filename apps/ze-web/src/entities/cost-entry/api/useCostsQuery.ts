import { useQuery } from "@tanstack/react-query";
import { getCostSummary } from "@ze/client";
import type { WebCostSummaryResponse } from "@ze/client";
import { queryKeys } from "@/shared/lib";

export function useCostsQuery() {
  return useQuery<WebCostSummaryResponse>({
    queryKey: queryKeys.costs,
    queryFn: async () => {
      const { data } = await getCostSummary();
      return data!;
    },
  });
}
