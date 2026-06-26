import { useMutation, useQueryClient } from "@tanstack/react-query";
import { reviewFacts } from "@ze/client";
import { queryKeys } from "@/shared/lib";
import type { MemoryFeedFilters } from "./useMemoryFeedQuery";

export function useReviewFactMutation(filters: MemoryFeedFilters) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: Parameters<typeof reviewFacts>[0]["body"]) =>
      reviewFacts({ body }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.memoryFeed(filters.type, filters.agent),
      });
    },
  });
}
