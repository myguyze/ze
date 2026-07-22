import { listLoops } from "@myguyze/ze-client";
import type { LoopListItem } from "@myguyze/ze-client";
import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/shared/lib";

export function useLoopsQuery(state?: string) {
  return useQuery<LoopListItem[]>({
    queryKey: queryKeys.loops(state),
    queryFn: async () => {
      const { data } = await listLoops({ query: state ? { state } : undefined });
      return data ?? [];
    },
  });
}
