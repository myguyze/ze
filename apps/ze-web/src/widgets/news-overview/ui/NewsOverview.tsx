import { Newspaper } from "lucide-react";
import { FloatingButton } from "@/features/open-context-overlay";
import { ArticleCard, useNewsQuery } from "@/entities/news-article";
import { EmptyState, ErrorState } from "@/shared/ui";

export function NewsOverview() {
  const { data: articles, isLoading, isError, refetch } = useNewsQuery();

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
