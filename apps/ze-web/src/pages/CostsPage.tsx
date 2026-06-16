import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/queryKeys";
import { type CostSummary } from "@/types/api";
import { FloatingButton } from "@/features/overlay/FloatingButton";
import { PageHeader } from "@/components/layout/PageHeader";
import { ErrorState } from "@/components/layout/ErrorState";
import { ListSkeleton } from "@/components/layout/ListSkeleton";

function formatAgentName(key: string): string {
  return key
    .replace(/_agent$/i, "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatUsd(usd: number): string {
  if (usd === 0) return "$0.00";
  if (usd < 0.0001) return "<$0.0001";
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(3)}`;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export function CostsPage() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: queryKeys.costs,
    queryFn: () => api.get<CostSummary>("/api/costs/summary"),
  });

  const sortedAgents = data
    ? Object.entries(data.by_agent).sort((a, b) => b[1].usd - a[1].usd)
    : [];

  const dailyAvg = data ? data.total_usd / 30 : 0;

  return (
    <div className="px-4 py-8 space-y-6 max-w-xl mx-auto">
      <PageHeader label="System" title="Usage" />

      {isLoading && <ListSkeleton />}

      {isError && (
        <ErrorState
          message="Could not load usage data."
          onRetry={() => void refetch()}
        />
      )}

      {!isError && data && (
        <>
          {/* Primary stats */}
          <div className="grid grid-cols-2 gap-3">
            <div className="p-4 rounded-[24px] border border-white/10">
              <p className="text-[36px] font-extralight text-white leading-none">
                {formatUsd(data.total_usd)}
              </p>
              <p className="mt-1 text-xs text-[#9a9a9a] tracking-wide">
                {data.period.toLowerCase()}
              </p>
            </div>
            <div className="p-4 rounded-[24px] border border-white/10">
              <p className="text-[36px] font-extralight text-white leading-none">
                {data.total_calls.toLocaleString()}
              </p>
              <p className="mt-1 text-xs text-[#9a9a9a] tracking-wide">
                LLM calls
              </p>
            </div>
          </div>

          {/* Secondary stats */}
          <div className="grid grid-cols-3 gap-2">
            <div className="px-3 py-2.5 rounded-[16px] bg-white/[0.03] border border-white/5">
              <p className="text-sm font-light text-white">{formatUsd(dailyAvg)}</p>
              <p className="text-[10px] text-[#9a9a9a] mt-0.5">per day</p>
            </div>
            <div className="px-3 py-2.5 rounded-[16px] bg-white/[0.03] border border-white/5">
              <p className="text-sm font-light text-white">
                {data.total_calls > 0 ? formatUsd(data.total_usd / data.total_calls) : "—"}
              </p>
              <p className="text-[10px] text-[#9a9a9a] mt-0.5">per call</p>
            </div>
            <div className="px-3 py-2.5 rounded-[16px] bg-white/[0.03] border border-white/5">
              <p className="text-sm font-light text-white">{formatTokens(data.total_tokens)}</p>
              <p className="text-[10px] text-[#9a9a9a] mt-0.5">tokens</p>
            </div>
          </div>

          {/* By agent */}
          {sortedAgents.length > 0 && (
            <div>
              <p className="text-xs font-semibold tracking-widest uppercase text-[#9a9a9a] mb-3">
                By agent
              </p>
              <div className="space-y-2">
                {sortedAgents.map(([agent, usage]) => {
                  const pct =
                    data.total_usd > 0 ? (usage.usd / data.total_usd) * 100 : 0;
                  const avgPerCall = usage.calls > 0 ? usage.usd / usage.calls : 0;
                  const inputPct =
                    usage.tokens > 0
                      ? Math.round((usage.prompt_tokens / usage.tokens) * 100)
                      : 0;

                  return (
                    <div
                      key={agent}
                      className="relative px-4 py-3 rounded-[24px] border border-white/10 overflow-hidden"
                    >
                      <div
                        className="absolute inset-y-0 left-0 bg-[#8052ff]/10 rounded-[24px] transition-all"
                        style={{ width: `${pct}%` }}
                      />
                      <div className="relative flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm text-white">{formatAgentName(agent)}</p>
                          <p className="text-[10px] text-[#9a9a9a] mt-0.5">
                            {usage.calls} {usage.calls === 1 ? "call" : "calls"}
                            {" · "}
                            {formatTokens(usage.tokens)} tok
                            {inputPct > 0 && <> · {inputPct}% input</>}
                          </p>
                        </div>
                        <div className="text-right flex-shrink-0">
                          <p className="text-sm text-white">{formatUsd(usage.usd)}</p>
                          <p className="text-[10px] text-[#9a9a9a] mt-0.5">
                            {pct.toFixed(1)}%
                            {avgPerCall > 0 && <> · {formatUsd(avgPerCall)}/call</>}
                          </p>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}

      <FloatingButton screen="costs" />
    </div>
  );
}
