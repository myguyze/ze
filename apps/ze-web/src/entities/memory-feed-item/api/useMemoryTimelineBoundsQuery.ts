import { useQuery } from "@tanstack/react-query";
import { getMemoryTimelineBounds } from "@myguyze/ze-client";
import type { TimelineBoundsResponse } from "@myguyze/ze-client";

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
