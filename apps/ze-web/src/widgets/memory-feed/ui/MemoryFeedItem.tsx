import { AlertTriangle, BookOpen, Sparkles } from "lucide-react";
import type { MemoryFeedItem as FeedItem } from "@myguyze/ze-client";
import { formatAgentName } from "@/entities/cost-entry";
import type { MemoryFeedFilters } from "@/entities/memory-feed-item";
import { relativeTime } from "../lib/format";
import { FactReviewActions } from "./FactReviewActions";

interface MemoryFeedItemProps {
  item: FeedItem;
  filters: MemoryFeedFilters;
}

function Pill({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "accent" | "danger" }) {
  const toneClass =
    tone === "accent"
      ? "border-plum-voltage/30 bg-plum-voltage/10 text-plum-voltage"
      : tone === "danger"
        ? "border-destructive/30 bg-destructive/10 text-destructive"
        : "border-white/10 bg-white/[0.04] text-smoke";
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-medium ${toneClass}`}>
      {children}
    </span>
  );
}

export function MemoryFeedItem({ item, filters }: MemoryFeedItemProps) {
  const isFact = item.type === "fact";
  const contradicted = isFact && !!item.contradicted;

  return (
    <div
      className={`group flex gap-3 px-4 py-3.5 rounded-pill border transition-colors ${
        contradicted
          ? "border-destructive/25 bg-destructive/[0.04]"
          : "border-white/10 bg-white/[0.02] hover:border-white/20 hover:bg-white/[0.035]"
      }`}
    >
      <div
        className={`flex items-center justify-center size-8 rounded-full shrink-0 border ${
          contradicted
            ? "bg-destructive/10 border-destructive/20 text-destructive"
            : isFact
              ? "bg-plum-voltage/10 border-plum-voltage/20 text-plum-voltage/80"
              : "bg-white/[0.06] border-white/10 text-smoke"
        }`}
      >
        {contradicted ? (
          <AlertTriangle className="size-3.5" />
        ) : isFact ? (
          <Sparkles className="size-3.5" />
        ) : (
          <BookOpen className="size-3.5" />
        )}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            {isFact ? (
              <p className={`text-sm leading-snug ${contradicted ? "line-through text-smoke" : "text-white"}`}>
                <span className="text-smoke">{item.key}:</span> {item.value}
              </p>
            ) : (
              <p className="text-sm leading-snug text-white line-clamp-2">
                {item.summary ?? item.prompt_snippet ?? "(no summary)"}
              </p>
            )}
          </div>
          <span className="text-[10px] text-smoke shrink-0 pt-0.5">{relativeTime(item.created_at)}</span>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 mt-2">
          <Pill>{formatAgentName(item.agent)}</Pill>
          {isFact && item.provenance === "synthesized" && (
            <Pill tone="accent">
              <Sparkles className="size-2.5" /> synthesized
            </Pill>
          )}
          {isFact && item.confidence != null && (
            <Pill>{Math.round(item.confidence * 100)}% confidence</Pill>
          )}
          {contradicted && <Pill tone="danger">contradicted</Pill>}
        </div>

        {isFact && !item.reviewed && !contradicted && (
          <FactReviewActions item={item} filters={filters} />
        )}
      </div>
    </div>
  );
}
