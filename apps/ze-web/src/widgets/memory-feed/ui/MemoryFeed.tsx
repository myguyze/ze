import { useEffect, useMemo, useRef } from "react";
import { Brain, Loader2 } from "lucide-react";
import { useMemoryFeedQuery } from "@/entities/memory-feed-item";
import type { MemoryFeedFilters } from "@/entities/memory-feed-item";
import { EmptyState, ErrorState, ListSkeleton } from "@/shared/ui";
import { dayGroupLabel } from "../lib/format";
import { MemoryFeedItem } from "./MemoryFeedItem";

interface MemoryFeedProps {
  filters: MemoryFeedFilters;
  asOf?: string;
  search?: string;
}

export function MemoryFeed({ filters, asOf, search }: MemoryFeedProps) {
  const sentinelRef = useRef<HTMLDivElement>(null);
  const { data, isLoading, isError, fetchNextPage, hasNextPage, isFetchingNextPage, refetch } =
    useMemoryFeedQuery(filters, asOf);

  const firstPage = data?.pages[0];
  const allItems = data?.pages.flatMap((p) => p.items) ?? [];

  const query = search?.trim().toLowerCase() ?? "";
  const filteredItems = useMemo(() => {
    if (!query) return allItems;
    return allItems.filter((item) => {
      const haystack = [item.key, item.value, item.summary, item.prompt_snippet, item.agent]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [allItems, query]);

  const groups = useMemo(() => {
    const map = new Map<string, typeof filteredItems>();
    for (const item of filteredItems) {
      const label = dayGroupLabel(item.created_at);
      const bucket = map.get(label);
      if (bucket) bucket.push(item);
      else map.set(label, [item]);
    }
    return Array.from(map.entries());
  }, [filteredItems]);

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
    return <ListSkeleton count={6} height="h-16" />;
  }

  if (isError) {
    return (
      <ErrorState
        message="Failed to load memory feed."
        onRetry={() => void refetch()}
      />
    );
  }

  if (!allItems.length) {
    return (
      <EmptyState
        icon={Brain}
        message="No memory items yet."
        detail="Facts and episodes Ze learns from your conversations will show up here."
      />
    );
  }

  if (!filteredItems.length) {
    return (
      <EmptyState icon={Brain} message="No memory items match your search." />
    );
  }

  return (
    <div className="space-y-6">
      {firstPage && (
        <p className="text-xs text-smoke">
          <span className="text-white font-medium">{firstPage.total_facts}</span> facts ·{" "}
          <span className="text-white font-medium">{firstPage.total_episodes}</span> episodes
        </p>
      )}

      {groups.map(([label, items]) => (
        <div key={label} className="space-y-2">
          <h3 className="text-[11px] font-semibold uppercase tracking-widest text-smoke/70 px-1">
            {label}
          </h3>
          <div className="space-y-2">
            {items.map((item) => (
              <MemoryFeedItem key={item.id} item={item} filters={filters} />
            ))}
          </div>
        </div>
      ))}

      <div ref={sentinelRef} className="h-1" />
      {isFetchingNextPage && (
        <div className="flex items-center justify-center gap-2 text-xs text-smoke py-2">
          <Loader2 className="size-3.5 animate-spin" /> Loading more…
        </div>
      )}
    </div>
  );
}
