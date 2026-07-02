import { useQuery } from "@tanstack/react-query";
import { searchSessions } from "@myguyze/ze-client";
import type { SessionSearchResult } from "@myguyze/ze-client";
import { queryKeys } from "@/shared/lib";

export function useSessionSearchQuery(query: string) {
  const trimmed = query.trim();

  return useQuery<SessionSearchResult[]>({
    queryKey: queryKeys.sessionSearch(trimmed),
    queryFn: async () => {
      const { data } = await searchSessions({
        query: { q: trimmed, limit: 20 },
      });
      return data ?? [];
    },
    enabled: trimmed.length >= 2,
  });
}
