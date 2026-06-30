import { useQuery } from "@tanstack/react-query";
import { getCostSummary } from "@myguyze/ze-client";
import type { WebCostSummaryResponse } from "@myguyze/ze-client";
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
