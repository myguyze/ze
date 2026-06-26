import { useEffect, useRef } from "react";
import { useMemoryFeedQuery } from "@/entities/memory-feed-item";
import type { MemoryFeedFilters } from "@/entities/memory-feed-item";
import { MemoryFeedItem } from "./MemoryFeedItem";

interface MemoryFeedProps {
  filters: MemoryFeedFilters;
}

export function MemoryFeed({ filters }: MemoryFeedProps) {
  const sentinelRef = useRef<HTMLDivElement>(null);
  const { data, isLoading, isError, fetchNextPage, hasNextPage, isFetchingNextPage, refetch } =
    useMemoryFeedQuery(filters);

  const firstPage = data?.pages[0];
  const allItems = data?.pages.flatMap((p) => p.items) ?? [];

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && hasNextPage && !isFetchingNextPage) {
          void fetchNextPage();
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-14 rounded-lg bg-white/5 animate-pulse" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="text-sm text-red-400 text-center py-8">
        Failed to load memory feed.{" "}
        <button onClick={() => void refetch()} className="underline">
          Retry
        </button>
      </div>
    );
  }

  if (!allItems.length) {
    return (
      <div className="text-sm text-smoke text-center py-12">
        No memory items yet.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {firstPage && (
        <p className="text-xs text-smoke mb-4">
          {firstPage.total_facts} facts · {firstPage.total_episodes} episodes
        </p>
      )}
      {allItems.map((item) => (
        <MemoryFeedItem key={item.id} item={item} filters={filters} />
      ))}
      <div ref={sentinelRef} className="h-1" />
      {isFetchingNextPage && (
        <div className="text-xs text-smoke text-center py-2">Loading more…</div>
      )}
    </div>
  );
}
