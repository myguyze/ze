import { useMemo, useState } from "react";
import type { MemoryFeedFilters } from "@/entities/memory-feed-item";
import { useMemoryActivityQuery, useMemoryTimelineBoundsQuery } from "@/entities/memory-feed-item";
import { MemoryFeed } from "@/widgets/memory-feed";
import { TimelineScrubber } from "@/widgets/timeline-scrubber";
import { FilterChips, SearchBar } from "@/shared/ui";
import type { FilterOption } from "@/shared/ui";

const TYPE_OPTIONS: FilterOption<MemoryFeedFilters["type"]>[] = [
  { label: "All", value: "all" },
  { label: "Facts", value: "fact" },
  { label: "Episodes", value: "episode" },
];

export function BrainMemoryPage() {
  const [filters, setFilters] = useState<MemoryFeedFilters>({ type: "all" });
  const [search, setSearch] = useState("");
  const [asOfDate, setAsOfDate] = useState<Date | null>(null);

  const { data: bounds } = useMemoryTimelineBoundsQuery();
  const earliest = bounds?.earliest ? new Date(bounds.earliest) : undefined;
  // Stable "now" snapshot — recomputing per render would churn the activity query key.
  const now = useMemo(() => new Date(), []);
  const { data: activity } = useMemoryActivityQuery(earliest, earliest ? now : undefined);

  const isPast = asOfDate !== null;
  const asOfIso = asOfDate ? asOfDate.toISOString() : undefined;

  return (
    <div className="px-6 md:px-10 py-8 space-y-6">
      <div
        className={`flex items-center gap-3 flex-wrap transition-opacity ${isPast ? "opacity-40 pointer-events-none" : ""}`}
      >
        <SearchBar
          value={search}
          onChange={setSearch}
          placeholder="Search memory…"
          className="w-64 shrink-0"
        />
        <FilterChips
          options={TYPE_OPTIONS}
          value={filters.type}
          onChange={(type) => setFilters((f) => ({ ...f, type }))}
        />
      </div>

      {bounds?.earliest && (
        <div className="rounded-pill border border-white/10 bg-white/[0.02] px-4 py-3">
          <TimelineScrubber
            earliest={new Date(bounds.earliest)}
            value={asOfDate}
            onChange={setAsOfDate}
            activity={activity?.days}
            activityMax={activity?.max_count}
          />
        </div>
      )}

      {isPast && asOfDate && (
        <div className="flex items-center gap-2 rounded-pill border border-warning/30 bg-warning/[0.06] px-4 py-2.5 text-xs text-warning">
          Viewing Ze's memory as of{" "}
          <span className="font-medium">
            {asOfDate.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}
          </span>
          {" "}— filters are disabled in snapshot view.
        </div>
      )}

      <MemoryFeed
        filters={isPast ? { type: "all" } : filters}
        asOf={asOfIso}
        search={isPast ? "" : search}
      />
    </div>
  );
}
