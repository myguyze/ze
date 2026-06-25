import { useQuery } from "@tanstack/react-query";
import { listNews } from "@ze/client";
import type { ArticleItem } from "@ze/client";
import { queryKeys } from "@/shared/lib";

export function useNewsQuery() {
  return useQuery<ArticleItem[]>({
    queryKey: queryKeys.news,
    queryFn: async () => {
      const { data } = await listNews({ query: { limit: 50 } });
      return data ?? [];
    },
    staleTime: 5 * 60_000,
  });
}
