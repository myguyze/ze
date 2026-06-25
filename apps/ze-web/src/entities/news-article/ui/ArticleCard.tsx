import type { ArticleItem } from "@ze/client";
import { AlertTriangle, ExternalLink, Tag } from "lucide-react";

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export function ArticleCard({ article }: { article: ArticleItem }) {
  const hasFlags = article.credibility_flags.length > 0;

  return (
    <a
      href={article.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group block border border-white/10 rounded-xl p-4 hover:border-white/20 hover:bg-white/[0.02] transition-colors"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <span className="text-[10px] font-semibold uppercase tracking-widest text-plum-voltage">
              {article.source_key}
            </span>
            <span className="text-[10px] text-smoke">{timeAgo(article.published_at)}</span>
          </div>

          <h3 className="text-sm font-medium text-white leading-snug group-hover:text-plum-voltage transition-colors line-clamp-2">
            {article.title}
          </h3>

          {article.summary && (
            <p className="text-xs text-smoke mt-1 line-clamp-2 leading-relaxed">
              {article.summary}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-2 mt-2">
            {article.tags.slice(0, 3).map((tag) => (
              <span
                key={tag}
                className="inline-flex items-center gap-1 text-[10px] text-smoke bg-white/5 px-2 py-0.5 rounded-full"
              >
                <Tag className="w-2.5 h-2.5" />
                {tag}
              </span>
            ))}

            {hasFlags && (
              <span
                className="inline-flex items-center gap-1 text-[10px] text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded-full"
                title={article.credibility_flags.map((f) => f.label).join(", ")}
              >
                <AlertTriangle className="w-2.5 h-2.5" />
                {article.credibility_flags[0].label}
                {article.credibility_flags.length > 1 &&
                  ` +${article.credibility_flags.length - 1}`}
              </span>
            )}
          </div>
        </div>

        <ExternalLink className="w-3.5 h-3.5 text-smoke flex-shrink-0 mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>
    </a>
  );
}
