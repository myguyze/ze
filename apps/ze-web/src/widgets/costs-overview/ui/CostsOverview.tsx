import { FloatingButton } from "@/features/open-context-overlay";
import { ActivityHeatmapPanel } from "@/widgets/activity-heatmap-panel";
import {
  formatAgentName,
  formatTokens,
  formatUsd,
  useCostsQuery,
  useCostAnomaliesQuery,
} from "@/entities/cost-entry";
import { PageHeader, ErrorState, ListSkeleton } from "@/shared/ui";
import type { CostAnomalyItem, DailyCostBucket } from "@myguyze/ze-client";

function formatRelativeTime(isoString: string): string {
  const diff = Date.now() - new Date(isoString).getTime();
  const hours = Math.floor(diff / 3_600_000);
  if (hours < 1) return "just now";
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function AnomalyPanel({ anomalies, isLoading }: { anomalies: CostAnomalyItem[]; isLoading: boolean }) {
  const hasAnomalies = anomalies.length > 0;

  return (
    <div className="space-y-2">
      <p className={`text-[10px] font-semibold tracking-widest uppercase ${hasAnomalies ? "text-amber-spark/80" : "text-smoke"}`}>
        Spend alerts
      </p>

      {!isLoading && !hasAnomalies && (
        <div className="px-3 py-3 rounded-2xl border border-white/[0.06] bg-white/[0.02] flex items-center gap-3">
          <div className="w-1.5 h-1.5 rounded-full bg-lichen flex-shrink-0" />
          <div>
            <p className="text-xs text-white/70">All clear — no unusual spend</p>
            <p className="text-[10px] text-smoke mt-0.5">
              Ze flags runs that cost an abnormal amount
            </p>
          </div>
        </div>
      )}

      {hasAnomalies && anomalies.map((a, i) => (
        <div
          key={i}
          className="px-3 py-3 rounded-2xl border border-amber-spark/20 bg-amber-spark/[0.04]"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm text-white">
                {formatAgentName(a.agent)}{" "}
                <span className="text-amber-spark font-medium">
                  {a.multiplier.toFixed(1)}×
                </span>{" "}
                <span className="text-smoke text-xs">over baseline</span>
              </p>
              <p className="text-[10px] text-smoke mt-0.5">
                ${a.run_cost_usd.toFixed(4)} vs ${a.baseline_cost_usd.toFixed(4)} median
                {" · "}
                {formatRelativeTime(a.detected_at)}
              </p>
            </div>
            <p className="text-xs text-amber-spark tabular-nums flex-shrink-0">
              ${a.run_cost_usd.toFixed(4)}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

function fillDays(by_day: DailyCostBucket[], days = 30): DailyCostBucket[] {
  const map = new Map(by_day.map((d) => [d.date, d]));
  const result: DailyCostBucket[] = [];
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    const key = d.toISOString().slice(0, 10);
    result.push(map.get(key) ?? { date: key, usd: 0, calls: 0 });
  }
  return result;
}

function SpendChart({ by_day }: { by_day: DailyCostBucket[] }) {
  const filled = fillDays(by_day);
  const max = Math.max(...filled.map((d) => d.usd), 0.000001);
  const peakIdx = filled.reduce(
    (best, d, i) => (d.usd > filled[best].usd ? i : best),
    0,
  );

  const W = 400;
  const H = 72;
  const n = filled.length;
  const gap = 2;
  const barW = Math.floor((W - gap * (n - 1)) / n);

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full"
      style={{ height: H }}
      aria-hidden="true"
    >
      {filled.map((d, i) => {
        const h = Math.max(2, (d.usd / max) * (H - 4));
        const x = i * (barW + gap);
        const y = H - h;
        const isPeak = i === peakIdx && d.usd > 0;
        const isRecent = i >= n - 3;
        const fill = isPeak
          ? "#ffb829"
          : isRecent && d.usd > 0
            ? "rgba(128,82,255,0.9)"
            : d.usd > 0
              ? "rgba(128,82,255,0.5)"
              : "rgba(255,255,255,0.05)";

        return (
          <rect
            key={d.date}
            x={x}
            y={y}
            width={barW}
            height={h}
            rx={1}
            fill={fill}
          />
        );
      })}
    </svg>
  );
}

function TokenSplit({
  prompt,
  completion,
}: {
  prompt: number;
  completion: number;
}) {
  const total = prompt + completion;
  if (total === 0) return null;
  const inputPct = Math.round((prompt / total) * 100);
  return (
    <div className="mt-1.5 space-y-0.5">
      <div className="flex h-[3px] rounded-full overflow-hidden gap-px">
        <div
          className="bg-plum-voltage/70 rounded-l-full"
          style={{ width: `${inputPct}%` }}
        />
        <div className="bg-white/15 rounded-r-full flex-1" />
      </div>
      <p className="text-[9px] text-smoke/50">
        {inputPct}% input · {100 - inputPct}% output
      </p>
    </div>
  );
}

function AgentRow({
  agent,
  usage,
  totalUsd,
}: {
  agent: string;
  usage: {
    usd: number;
    tokens: number;
    calls: number;
    prompt_tokens: number;
    completion_tokens: number;
  };
  totalUsd: number;
}) {
  const pct = totalUsd > 0 ? (usage.usd / totalUsd) * 100 : 0;
  const avgPerCall = usage.calls > 0 ? usage.usd / usage.calls : 0;

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 mb-1.5">
        <p className="text-sm text-white">{formatAgentName(agent)}</p>
        <p className="text-sm text-white tabular-nums">{formatUsd(usage.usd)}</p>
      </div>
      <div className="relative h-[3px] rounded-full bg-white/[0.06] overflow-hidden">
        <div
          className="absolute inset-y-0 left-0 bg-plum-voltage rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-smoke">
        <span className="tabular-nums">{pct.toFixed(1)}%</span>
        <span className="text-smoke/30">·</span>
        <span>{usage.calls} {usage.calls === 1 ? "call" : "calls"}</span>
        <span className="text-smoke/30">·</span>
        <span className="tabular-nums">{formatTokens(usage.tokens)} tok</span>
        {avgPerCall > 0 && (
          <>
            <span className="text-smoke/30">·</span>
            <span className="tabular-nums">{formatUsd(avgPerCall)}/call</span>
          </>
        )}
      </div>
      <TokenSplit
        prompt={usage.prompt_tokens}
        completion={usage.completion_tokens}
      />
    </div>
  );
}

export function CostsOverview() {
  const { data, isLoading, isError, refetch } = useCostsQuery();
  const { data: anomaliesData, isLoading: anomaliesLoading } = useCostAnomaliesQuery();

  const anomalies = anomaliesData?.anomalies ?? [];
  const sortedAgents = data
    ? Object.entries(data.by_agent).sort((a, b) => b[1].usd - a[1].usd)
    : [];

  const dailyAvg = data ? data.total_usd / 30 : 0;

  if (isLoading) {
    return (
      <div className="px-6 py-8">
        <PageHeader label="System" title="Usage" />
        <div className="mt-8">
          <ListSkeleton />
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="px-6 py-8">
        <PageHeader label="System" title="Usage" />
        <div className="mt-8">
          <ErrorState
            message="Could not load usage data."
            onRetry={() => void refetch()}
          />
        </div>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="px-6 py-8 space-y-8">
      <PageHeader label="System" title="Usage" />

      <div className="grid grid-cols-1 xl:grid-cols-[5fr_7fr] gap-8">
        {/* Left: hero + chart + stats */}
        <div className="flex flex-col gap-6">
          {/* Hero spend */}
          <div>
            <p className="text-[64px] font-extralight leading-none tracking-tight text-white">
              {formatUsd(data.total_usd)}
            </p>
            <p className="mt-2 text-[10px] text-smoke tracking-widest uppercase">
              {data.period}
            </p>
          </div>

          {/* Daily histogram */}
          {data.by_day.length > 0 && (
            <div>
              <SpendChart by_day={data.by_day} />
              <div className="flex justify-between mt-1">
                <p className="text-[9px] text-smoke/40">30 days ago</p>
                <p className="text-[9px] text-smoke/40">today</p>
              </div>
            </div>
          )}

          {/* Secondary stats */}
          <div className="grid grid-cols-3 gap-2">
            <div className="px-3 py-3 rounded-2xl bg-white/[0.03] border border-white/[0.06]">
              <p className="text-base font-light text-white tabular-nums">
                {formatUsd(dailyAvg)}
              </p>
              <p className="text-[10px] text-smoke mt-0.5">per day</p>
            </div>
            <div className="px-3 py-3 rounded-2xl bg-white/[0.03] border border-white/[0.06]">
              <p className="text-base font-light text-white tabular-nums">
                {data.total_calls > 0
                  ? formatUsd(data.total_usd / data.total_calls)
                  : "—"}
              </p>
              <p className="text-[10px] text-smoke mt-0.5">per call</p>
            </div>
            <div className="px-3 py-3 rounded-2xl bg-white/[0.03] border border-white/[0.06]">
              <p className="text-base font-light text-white tabular-nums">
                {formatTokens(data.total_tokens)}
              </p>
              <p className="text-[10px] text-smoke mt-0.5">tokens</p>
            </div>
          </div>

          <AnomalyPanel anomalies={anomalies} isLoading={anomaliesLoading} />

          <p className="text-[10px] text-smoke/30">
            {data.total_calls.toLocaleString()} LLM{" "}
            {data.total_calls === 1 ? "call" : "calls"} total
          </p>
        </div>

        {/* Right: agent breakdown */}
        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-5">
            <p className="text-[10px] font-semibold tracking-widest uppercase text-smoke">
              By agent
            </p>
            {sortedAgents.length === 0 ? (
              <p className="text-sm text-smoke">No agent data yet.</p>
            ) : (
              sortedAgents.map(([agent, usage]) => (
                <AgentRow
                  key={agent}
                  agent={agent}
                  usage={usage}
                  totalUsd={data.total_usd}
                />
              ))
            )}
          </div>
        </div>
      </div>

      <ActivityHeatmapPanel />

      <FloatingButton screen="costs" />
    </div>
  );
}
