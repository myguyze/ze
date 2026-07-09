import type { MemoryFeedItem as FeedItem } from "@myguyze/ze-client";
import type { MemoryFeedFilters } from "@/entities/memory-feed-item";
import { relativeTime } from "../lib/format";
import { FactReviewActions } from "./FactReviewActions";

interface MemoryFeedItemProps {
  item: FeedItem;
  filters: MemoryFeedFilters;
}

export function MemoryFeedItem({ item, filters }: MemoryFeedItemProps) {
  if (item.type === "fact") {
    return (
      <div
        className={`px-4 py-3 rounded-lg border ${
          item.contradicted
            ? "border-destructive/30 bg-destructive/5"
            : "border-white/10 bg-white/[0.03]"
        }`}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <span className={`text-sm ${item.contradicted ? "line-through text-smoke" : "text-white"}`}>
              <span className="text-smoke">{item.key}:</span>{" "}
              {item.value}
            </span>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {item.provenance === "synthesized" && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-plum-voltage/20 text-plum-voltage">
                synthesized
              </span>
            )}
            {item.confidence != null && (
              <span className="text-[10px] text-smoke">
                {Math.round(item.confidence * 100)}%
              </span>
            )}
            {item.contradicted && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-destructive/20 text-destructive">
                contradicted
              </span>
            )}
            <span className="text-[10px] text-smoke">{relativeTime(item.created_at)}</span>
          </div>
        </div>
        {!item.reviewed && !item.contradicted && (
          <FactReviewActions item={item} filters={filters} />
        )}
      </div>
    );
  }

  return (
    <div className="px-4 py-3 rounded-lg border border-white/10 bg-white/[0.03]">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-white">
            {item.summary ?? item.prompt_snippet ?? "(no summary)"}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/10 text-smoke">
            {item.agent}
          </span>
          <span className="text-[10px] text-smoke">{relativeTime(item.created_at)}</span>
        </div>
      </div>
    </div>
  );
}
