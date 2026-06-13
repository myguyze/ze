import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { FloatingButton } from "@/overlay/FloatingButton";

interface CostSummary {
  total_usd: number;
  total_tokens: number;
  by_agent: Record<string, { usd: number; tokens: number }>;
  period: string;
}

export function CostsScreen() {
  const { data, isLoading } = useQuery({
    queryKey: ["costs"],
    queryFn: () => api.get<CostSummary>("/api/costs/summary"),
  });

  return (
    <div className="px-4 py-8 space-y-6">
      <div>
        <p className="text-xs font-semibold tracking-widest uppercase text-[#9a9a9a] mb-1">
          Costs
        </p>
        <p className="text-2xl font-extralight text-white">Usage</p>
      </div>

      {isLoading && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 rounded-[24px] border border-white/10 animate-pulse" />
          ))}
        </div>
      )}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <div className="p-4 rounded-[24px] border border-white/10">
              <p className="text-[36px] font-extralight text-white leading-none">
                ${data.total_usd.toFixed(4)}
              </p>
              <p className="mt-1 text-xs text-[#9a9a9a] tracking-wide">{data.period}</p>
            </div>
            <div className="p-4 rounded-[24px] border border-white/10">
              <p className="text-[36px] font-extralight text-white leading-none">
                {(data.total_tokens / 1000).toFixed(1)}k
              </p>
              <p className="mt-1 text-xs text-[#9a9a9a] tracking-wide">tokens</p>
            </div>
          </div>

          <div>
            <p className="text-xs font-semibold tracking-widest uppercase text-[#9a9a9a] mb-3">
              By agent
            </p>
            <div className="space-y-2">
              {Object.entries(data.by_agent)
                .sort((a, b) => b[1].usd - a[1].usd)
                .map(([agent, cost]) => (
                  <div
                    key={agent}
                    className="flex items-center justify-between px-4 py-3 rounded-[24px] border border-white/10"
                  >
                    <p className="text-sm text-white capitalize">{agent}</p>
                    <div className="text-right">
                      <p className="text-sm text-white">${cost.usd.toFixed(4)}</p>
                      <p className="text-xs text-[#9a9a9a]">{(cost.tokens / 1000).toFixed(1)}k tok</p>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        </>
      )}

      <FloatingButton screen="costs" />
    </div>
  );
}
