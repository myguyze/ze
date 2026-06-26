import { useQuery } from "@tanstack/react-query";
import { getActivityHeatmap } from "@ze/client";
import type { ActivityHeatmapResponse } from "@ze/client";
import { queryKeys } from "@/shared/lib";

export function useActivityHeatmapQuery(start?: string, end?: string) {
  return useQuery<ActivityHeatmapResponse>({
    queryKey: queryKeys.activityHeatmap(start, end),
    queryFn: async () => {
      const { data, error } = await getActivityHeatmap({
        query: { start, end },
      });
      if (error) throw error;
      return data!;
    },
  });
}
