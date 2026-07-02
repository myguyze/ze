import { useMemo } from "react";
import { useDataDomainsQuery } from "@/entities/data-domain";
import { settingsDataPath } from "@/shared/config";
import { useTopBarQuickActions } from "@/shared/lib";
import { PageHeader, ErrorState, ListSkeleton, TopBarQuickActionLink } from "@/shared/ui";
import type { DataDomainItem } from "@myguyze/ze-client";

import {
  buildCategorySegments,
  groupByPrefix,
  largestCategory,
} from "../lib/aggregate";
import { capitalize, formatBytes, formatCount, shortDomainName } from "../lib/format";
import { StorageDonutChart } from "./StorageDonutChart";

function StatCard({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="px-3 py-3 rounded-2xl bg-white/[0.03] border border-white/[0.06]">
      <p className="text-base font-light text-white tabular-nums">{value}</p>
      <p className="text-[10px] text-smoke mt-0.5">{label}</p>
      {hint && <p className="text-[9px] text-smoke/50 mt-0.5 truncate">{hint}</p>}
    </div>
  );
}

function DomainRow({
  domain,
  totalBytes,
}: {
  domain: DataDomainItem;
  totalBytes: number;
}) {
  const pct = totalBytes > 0 ? (domain.size_bytes / totalBytes) * 100 : 0;
  const showSize = domain.size_bytes > 0;

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 mb-1.5">
        <div className="flex items-center gap-2 min-w-0">
          <p className="font-mono text-xs text-white truncate">
            {shortDomainName(domain.name)}
          </p>
          {domain.importable && (
            <span className="text-[9px] font-semibold tracking-widest uppercase text-lichen/70 border border-lichen/20 rounded px-1 py-0.5 flex-shrink-0">
              importable
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0 text-[10px] tabular-nums">
          {showSize && <span className="text-white">{formatBytes(domain.size_bytes)}</span>}
          <span className="text-smoke">{formatCount(domain.count)}</span>
        </div>
      </div>
      {showSize && (
        <div className="relative h-[3px] rounded-full bg-white/[0.06] overflow-hidden">
          <div
            className="absolute inset-y-0 left-0 bg-plum-voltage rounded-full transition-all duration-500"
            style={{ width: `${Math.max(pct, 0.5)}%` }}
          />
        </div>
      )}
      {showSize && (
        <p className="mt-1 text-[9px] text-smoke/50 tabular-nums">{pct.toFixed(1)}% of storage</p>
      )}
    </div>
  );
}

export function DataOverview() {
  const { data, isLoading, isError, refetch } = useDataDomainsQuery();

  const quickActions = useMemo(
    () => (
      <TopBarQuickActionLink to={settingsDataPath()}>
        Export / import
      </TopBarQuickActionLink>
    ),
    [],
  );
  useTopBarQuickActions(quickActions);

  if (isLoading) {
    return (
      <div className="px-6 py-8">
        <PageHeader label="System" title="Your data" />
        <div className="mt-8">
          <ListSkeleton count={8} />
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="px-6 py-8">
        <PageHeader label="System" title="Your data" />
        <div className="mt-8">
          <ErrorState message="Could not load data domains." onRetry={() => void refetch()} />
        </div>
      </div>
    );
  }

  const groups = groupByPrefix(data.domains);
  const segments = buildCategorySegments(data.domains, data.total_size_bytes);
  const topCategory = largestCategory(segments, data.total_size_bytes);

  return (
    <div className="px-6 py-8 h-full flex flex-col gap-8">
      <PageHeader label="System" title="Your data" />

      <div className="flex-1 grid grid-cols-[5fr_7fr] gap-8 min-h-0">
        <div className="flex flex-col gap-6">
          <div>
            <p className="text-[64px] font-extralight leading-none tracking-tight text-white">
              {formatBytes(data.total_size_bytes)}
            </p>
            <p className="mt-2 text-[10px] text-smoke tracking-widest uppercase">
              total storage
            </p>
          </div>

          <div className="px-4 py-4 rounded-2xl border border-white/[0.06] bg-white/[0.02]">
            <p className="text-[10px] font-semibold tracking-widest uppercase text-smoke mb-4">
              By category
            </p>
            <StorageDonutChart segments={segments} totalBytes={data.total_size_bytes} />
          </div>

          <div className="grid grid-cols-3 gap-2">
            <StatCard label="domains" value={String(data.domains.length)} />
            <StatCard
              label="records"
              value={data.total_records.toLocaleString()}
            />
            <StatCard
              label="largest"
              value={topCategory ? `${topCategory.pct.toFixed(0)}%` : "—"}
              hint={topCategory ? capitalize(topCategory.label) : undefined}
            />
          </div>

          <p className="text-[10px] text-smoke/30">
            Disk usage from Postgres table sizes (data + indexes)
          </p>
        </div>

        <div className="flex flex-col gap-6 overflow-y-auto min-h-0">
          <p className="text-[10px] font-semibold tracking-widest uppercase text-smoke">
            By domain
          </p>

          <div className="flex flex-col gap-6">
            {Object.entries(groups)
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([prefix, domains]) => (
                <div key={prefix} className="space-y-4">
                  <p className="text-[10px] font-semibold tracking-widest uppercase text-smoke/70">
                    {capitalize(prefix)}
                  </p>
                  <div className="space-y-4">
                    {domains.map((d) => (
                      <DomainRow
                        key={d.name}
                        domain={d}
                        totalBytes={data.total_size_bytes}
                      />
                    ))}
                  </div>
                </div>
              ))}
          </div>
        </div>
      </div>
    </div>
  );
}
