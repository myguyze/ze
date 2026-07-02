import { useMemo } from "react";
import type { DataDomainItem } from "@myguyze/ze-client";
import { useDataDomainsQuery } from "@/entities/data-domain";
import { settingsDataPath } from "@/shared/config";
import { useTopBarQuickActions } from "@/shared/lib";
import {
  BreakdownGroup,
  BreakdownItem,
  BreakdownPanel,
  DashboardGrid,
  DashboardGridAside,
  DashboardGridMain,
  DashboardHero,
  DashboardSectionTitle,
  DashboardShell,
  DashboardStatCard,
  MetricProgressBar,
  SectionPanel,
  TopBarQuickActionLink,
} from "@/shared/ui";

import {
  buildCategorySegments,
  groupByPrefix,
  largestCategory,
} from "../lib/aggregate";
import { capitalize, formatBytes, formatCount, shortDomainName } from "../lib/format";
import { StorageDonutChart } from "./StorageDonutChart";

function DomainBreakdownItem({
  domain,
  totalBytes,
}: {
  domain: DataDomainItem;
  totalBytes: number;
}) {
  const pct = totalBytes > 0 ? (domain.size_bytes / totalBytes) * 100 : 0;
  const showSize = domain.size_bytes > 0;

  return (
    <BreakdownItem
      header={
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
      }
      meta={
        <>
          {showSize && <span className="text-white">{formatBytes(domain.size_bytes)}</span>}
          <span className="text-smoke">{formatCount(domain.count)}</span>
        </>
      }
    >
      {showSize && (
        <>
          <MetricProgressBar pct={pct} />
          <p className="mt-1.5 text-[9px] text-smoke/50 tabular-nums">
            {pct.toFixed(1)}% of storage
          </p>
        </>
      )}
    </BreakdownItem>
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

  const groups = data ? groupByPrefix(data.domains) : {};
  const segments = data ? buildCategorySegments(data.domains, data.total_size_bytes) : [];
  const topCategory = data ? largestCategory(segments, data.total_size_bytes) : null;
  const sortedGroups = Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));

  return (
    <DashboardShell
      className="h-full flex flex-col min-h-0"
      isLoading={isLoading}
      isError={isError || !data}
      errorMessage="Could not load data domains."
      onRetry={() => void refetch()}
      skeletonCount={8}
    >
      {data && (
        <DashboardGrid className="flex-1 min-h-0">
          <DashboardGridMain>
            <DashboardHero value={formatBytes(data.total_size_bytes)} caption="total storage" />

            <SectionPanel>
              <DashboardSectionTitle>By category</DashboardSectionTitle>
              <StorageDonutChart segments={segments} totalBytes={data.total_size_bytes} />
            </SectionPanel>

            <div className="grid grid-cols-3 gap-2">
              <DashboardStatCard label="domains" value={String(data.domains.length)} />
              <DashboardStatCard
                label="records"
                value={data.total_records.toLocaleString()}
              />
              <DashboardStatCard
                label="largest"
                value={topCategory ? `${topCategory.pct.toFixed(0)}%` : "—"}
                hint={topCategory ? capitalize(topCategory.label) : undefined}
              />
            </div>

            <p className="text-[10px] text-smoke/30">
              Disk usage from Postgres table sizes (data + indexes)
            </p>
          </DashboardGridMain>

          <DashboardGridAside className="min-h-0 xl:h-full">
            <BreakdownPanel title="By domain">
              <div className="flex flex-col gap-4">
                {sortedGroups.map(([prefix, domains]) => {
                  const totalSize = domains.reduce((sum, d) => sum + d.size_bytes, 0);
                  const totalCount = domains.reduce((sum, d) => sum + (d.count ?? 0), 0);

                  return (
                    <BreakdownGroup
                      key={prefix}
                      title={capitalize(prefix)}
                      summary={
                        <>
                          {domains.length} {domains.length === 1 ? "domain" : "domains"}
                          {totalCount > 0 && ` · ${totalCount.toLocaleString()} records`}
                        </>
                      }
                      collapsedHint={
                        totalSize > 0
                          ? `${formatBytes(totalSize)} across ${domains.length} domains`
                          : `${domains.length} domains in this group`
                      }
                    >
                      {domains.map((domain) => (
                        <DomainBreakdownItem
                          key={domain.name}
                          domain={domain}
                          totalBytes={data.total_size_bytes}
                        />
                      ))}
                    </BreakdownGroup>
                  );
                })}
              </div>
            </BreakdownPanel>
          </DashboardGridAside>
        </DashboardGrid>
      )}
    </DashboardShell>
  );
}
