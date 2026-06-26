import { useState } from "react";
import type { MemoryFeedFilters } from "@/entities/memory-feed-item";
import { MemoryFeed } from "@/widgets/memory-feed";
import { PageHeader } from "@/shared/ui";

const TYPE_OPTIONS: { label: string; value: MemoryFeedFilters["type"] }[] = [
  { label: "All", value: "all" },
  { label: "Facts", value: "fact" },
  { label: "Episodes", value: "episode" },
];

export function BrainMemoryPage() {
  const [filters, setFilters] = useState<MemoryFeedFilters>({ type: "all" });

  return (
    <div className="px-4 py-8 space-y-6">
      <div className="flex items-center justify-between gap-4">
        <PageHeader label="Brain" title="Memory" />
        <div className="flex items-center gap-1 rounded-lg border border-white/10 p-1">
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
      <MemoryFeed filters={filters} />
    </div>
  );
}
