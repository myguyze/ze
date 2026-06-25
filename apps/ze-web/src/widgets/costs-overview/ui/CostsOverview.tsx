import { FloatingButton } from "@/features/open-context-overlay";
import {
  formatAgentName,
  formatTokens,
  formatUsd,
  useCostsQuery,
} from "@/entities/cost-entry";
import { PageHeader, ErrorState, ListSkeleton } from "@/shared/ui";

export function CostsOverview() {
  const { data, isLoading, isError, refetch } = useCostsQuery();

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
          <div className="grid grid-cols-2 gap-3">
            <div className="p-4 rounded-pill border border-white/10">
              <p className="text-[36px] font-extralight text-white leading-none">
                {formatUsd(data.total_usd)}
              </p>
              <p className="mt-1 text-xs text-smoke tracking-wide">
                {data.period.toLowerCase()}
              </p>
            </div>
            <div className="p-4 rounded-pill border border-white/10">
              <p className="text-[36px] font-extralight text-white leading-none">
                {data.total_calls.toLocaleString()}
              </p>
              <p className="mt-1 text-xs text-smoke tracking-wide">LLM calls</p>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2">
            <div className="px-3 py-2.5 rounded-[16px] bg-white/[0.03] border border-white/5">
              <p className="text-sm font-light text-white">{formatUsd(dailyAvg)}</p>
              <p className="text-[10px] text-smoke mt-0.5">per day</p>
            </div>
            <div className="px-3 py-2.5 rounded-[16px] bg-white/[0.03] border border-white/5">
              <p className="text-sm font-light text-white">
                {data.total_calls > 0 ? formatUsd(data.total_usd / data.total_calls) : "—"}
              </p>
              <p className="text-[10px] text-smoke mt-0.5">per call</p>
            </div>
            <div className="px-3 py-2.5 rounded-[16px] bg-white/[0.03] border border-white/5">
              <p className="text-sm font-light text-white">{formatTokens(data.total_tokens)}</p>
              <p className="text-[10px] text-smoke mt-0.5">tokens</p>
            </div>
          </div>

          {sortedAgents.length > 0 && (
            <div>
              <p className="text-xs font-semibold tracking-widest uppercase text-smoke mb-3">
                By agent
              </p>
              <div className="space-y-2">
                {sortedAgents.map(([agent, usage]) => {
                  const pct = data.total_usd > 0 ? (usage.usd / data.total_usd) * 100 : 0;
                  const avgPerCall = usage.calls > 0 ? usage.usd / usage.calls : 0;
                  const inputPct =
                    usage.tokens > 0
                      ? Math.round((usage.prompt_tokens / usage.tokens) * 100)
                      : 0;

                  return (
                    <div
                      key={agent}
                      className="relative px-4 py-3 rounded-pill border border-white/10 overflow-hidden"
                    >
                      <div
                        className="absolute inset-y-0 left-0 bg-plum-voltage/10 rounded-pill transition-all"
                        style={{ width: `${pct}%` }}
                      />
                      <div className="relative flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm text-white">{formatAgentName(agent)}</p>
                          <p className="text-[10px] text-smoke mt-0.5">
                            {usage.calls} {usage.calls === 1 ? "call" : "calls"}
                            {" · "}
                            {formatTokens(usage.tokens)} tok
                            {inputPct > 0 && <> · {inputPct}% input</>}
                          </p>
                        </div>
                        <div className="text-right flex-shrink-0">
                          <p className="text-sm text-white">{formatUsd(usage.usd)}</p>
                          <p className="text-[10px] text-smoke mt-0.5">
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
