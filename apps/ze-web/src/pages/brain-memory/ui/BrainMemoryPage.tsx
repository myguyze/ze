import { useState } from "react";
import type { MemoryFeedFilters } from "@/entities/memory-feed-item";
import { useMemoryTimelineBoundsQuery } from "@/entities/memory-feed-item";
import { MemoryFeed } from "@/widgets/memory-feed";
import { TimelineScrubber } from "@/widgets/timeline-scrubber";
import { PageHeader } from "@/shared/ui";

const TYPE_OPTIONS: { label: string; value: MemoryFeedFilters["type"] }[] = [
  { label: "All", value: "all" },
  { label: "Facts", value: "fact" },
  { label: "Episodes", value: "episode" },
];

export function BrainMemoryPage() {
  const [filters, setFilters] = useState<MemoryFeedFilters>({ type: "all" });
  const [asOfDate, setAsOfDate] = useState<Date | null>(null);

  const { data: bounds } = useMemoryTimelineBoundsQuery();

  const isPast = asOfDate !== null;
  const asOfIso = asOfDate ? asOfDate.toISOString() : undefined;

  return (
    <div className="px-4 py-8 space-y-6">
      <div className="flex items-center justify-between gap-4">
        <PageHeader label="Brain" title="Memory" />
        <div className={`flex items-center gap-1 rounded-lg border border-white/10 p-1 transition-opacity ${isPast ? "opacity-40 pointer-events-none" : ""}`}>
          {TYPE_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setFilters((f) => ({ ...f, type: opt.value }))}
              className={`px-3 py-1 rounded text-xs transition-colors ${
                filters.type === opt.value
                  ? "bg-plum-voltage/20 text-white"
                  : "text-smoke hover:text-white"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {bounds?.earliest && (
        <TimelineScrubber
          earliest={new Date(bounds.earliest)}
          value={asOfDate}
          onChange={setAsOfDate}
        />
      )}

      {isPast && asOfDate && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-400/30 bg-amber-400/[0.06] px-3 py-2 text-xs text-amber-300">
          Viewing Ze's memory as of{" "}
          <span className="font-medium">
            {asOfDate.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}
          </span>
          {" "}— filters are disabled in snapshot view.
        </div>
      )}

      <MemoryFeed filters={isPast ? { type: "all" } : filters} asOf={asOfIso} />
    </div>
  );
}
