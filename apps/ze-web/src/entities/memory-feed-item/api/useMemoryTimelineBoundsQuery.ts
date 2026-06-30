import { useQuery } from "@tanstack/react-query";
import { getMemoryTimelineBounds } from "@ze/client";
import type { TimelineBoundsResponse } from "@ze/client";

export function useMemoryTimelineBoundsQuery() {
  return useQuery({
    queryKey: ["memory-timeline-bounds"],
    queryFn: async () => {
      const { data } = await getMemoryTimelineBounds({});
      return data as TimelineBoundsResponse;
    },
    staleTime: 60_000,
  });
}
