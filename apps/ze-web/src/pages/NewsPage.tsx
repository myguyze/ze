import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ExternalLink, Newspaper, Tag } from "lucide-react";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/queryKeys";
import { type Article } from "@/types/api";
import { FloatingButton } from "@/features/overlay/FloatingButton";
import { EmptyState } from "@/components/layout/EmptyState";
import { ErrorState } from "@/components/layout/ErrorState";

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function ArticleCard({ article }: { article: Article }) {
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

export function NewsPage() {
  const { data: articles, isLoading, isError, refetch } = useQuery<Article[]>({
    queryKey: queryKeys.news,
    queryFn: () => api.get<Article[]>("/api/news?limit=50"),
    staleTime: 5 * 60_000,
  });

  return (
    <div className="px-4 py-6 max-w-2xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <Newspaper className="w-5 h-5 text-plum-voltage" />
        <h1 className="text-lg font-semibold text-white">News</h1>
      </div>

      {isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="border border-white/10 rounded-xl p-4 animate-pulse">
              <div className="h-2.5 bg-white/10 rounded w-24 mb-2" />
              <div className="h-4 bg-white/10 rounded w-3/4 mb-1.5" />
              <div className="h-3 bg-white/10 rounded w-full mb-1" />
              <div className="h-3 bg-white/10 rounded w-2/3" />
            </div>
          ))}
        </div>
      )}

      {isError && (
        <ErrorState
          message="Could not load news."
          detail="Check that the news sources are configured."
          onRetry={() => void refetch()}
        />
      )}

      {!isLoading && !isError && articles?.length === 0 && (
        <EmptyState
          icon={Newspaper}
          message="No articles yet."
          detail="Articles are fetched from your configured RSS sources every 30 minutes."
        />
      )}

      {!isError && articles && articles.length > 0 && (
        <div className="space-y-3">
          {articles.map((article) => (
            <ArticleCard key={article.url} article={article} />
          ))}
        </div>
      )}

      <FloatingButton screen="news" />
    </div>
  );
}
