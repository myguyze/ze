import type { SessionSchema, SessionSearchResult } from "@myguyze/ze-client";
import { useEffect, useRef, useState } from "react";
import {
  SessionRow,
  useSession,
  useSessionSearchQuery,
  useSessionsQuery,
} from "@/entities/session";

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}

function searchResultToSession(result: SessionSearchResult): SessionSchema {
  return {
    id: result.id,
    title: result.title,
    preview: result.preview,
    title_source: result.title_source,
    created_at: result.created_at,
    last_active_at: result.last_active_at,
  };
}

interface SessionListProps {
  searchQuery: string;
}

export function SessionList({ searchQuery }: SessionListProps) {
  const threadId = useSession((s) => s.threadId);
  const selectSession = useSession((s) => s.selectSession);
  const debouncedQuery = useDebouncedValue(searchQuery, 300);
  const loadMoreRef = useRef<HTMLDivElement>(null);

  const isSearching = debouncedQuery.trim().length >= 2;

  const {
    data: browsePages,
    isLoading: browseLoading,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
  } = useSessionsQuery();

  const { data: searchResults, isLoading: searchLoading } = useSessionSearchQuery(debouncedQuery);

  useEffect(() => {
    if (isSearching) return;
    const node = loadMoreRef.current;
    if (!node || !hasNextPage) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && !isFetchingNextPage) {
          void fetchNextPage();
        }
      },
      { rootMargin: "120px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [fetchNextPage, hasNextPage, isFetchingNextPage, isSearching]);

  const browseSessions = browsePages?.pages.flatMap((page) => page.items) ?? [];
  const isLoading = isSearching ? searchLoading : browseLoading;

  return (
    <div className="space-y-2 px-3 py-3">
      {isLoading &&
        [1, 2, 3].map((i) => (
          <div key={i} className="h-[4.5rem] animate-pulse rounded-pill border border-white/10 bg-white/[0.02]" />
        ))}

      {!isLoading && isSearching && (searchResults?.length ?? 0) === 0 && (
        <p className="px-3 py-8 text-center text-sm text-smoke">No conversations found.</p>
      )}

      {!isLoading && !isSearching && browseSessions.length === 0 && (
        <p className="px-3 py-8 text-center text-sm text-smoke">No past sessions yet.</p>
      )}

      {isSearching &&
        searchResults?.map((result) => (
          <SessionRow
            key={result.id}
            session={searchResultToSession(result)}
            active={result.id === threadId}
            onSelect={() => selectSession(result.id)}
            searchSnippet={result.snippet}
            matchSource={result.match_source}
          />
        ))}

      {!isSearching &&
        browseSessions.map((session) => (
          <SessionRow
            key={session.id}
            session={session}
            active={session.id === threadId}
            onSelect={() => selectSession(session.id)}
          />
        ))}

      {!isSearching && hasNextPage && (
        <div ref={loadMoreRef} className="flex justify-center py-2">
          {isFetchingNextPage && <span className="text-[10px] text-smoke/80">Loading more…</span>}
        </div>
      )}
    </div>
  );
}
