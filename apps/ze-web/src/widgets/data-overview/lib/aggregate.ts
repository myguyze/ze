import type { DataDomainItem } from "@myguyze/ze-client";

import { domainPrefix } from "./format";

export type CategorySegment = {
  label: string;
  bytes: number;
  color: string;
};

const CATEGORY_COLORS = [
  "rgba(128,82,255,0.9)",
  "rgba(134,191,87,0.85)",
  "rgba(255,184,41,0.9)",
  "rgba(96,165,250,0.85)",
  "rgba(244,114,182,0.85)",
  "rgba(45,212,191,0.85)",
  "rgba(251,146,60,0.85)",
  "rgba(255,255,255,0.45)",
] as const;

const OTHER_COLOR = "rgba(255,255,255,0.2)";
const MIN_SEGMENT_PCT = 2;

export function groupByPrefix(domains: DataDomainItem[]): Record<string, DataDomainItem[]> {
  const groups: Record<string, DataDomainItem[]> = {};
  for (const d of domains) {
    const prefix = domainPrefix(d.name);
    (groups[prefix] ??= []).push(d);
  }
  for (const domainsInGroup of Object.values(groups)) {
    domainsInGroup.sort((a, b) => b.size_bytes - a.size_bytes);
  }
  return groups;
}

export function buildCategorySegments(
  domains: DataDomainItem[],
  totalBytes: number,
): CategorySegment[] {
  if (totalBytes === 0) return [];

  const byPrefix = new Map<string, number>();
  for (const d of domains) {
    if (d.size_bytes <= 0) continue;
    const prefix = domainPrefix(d.name);
    byPrefix.set(prefix, (byPrefix.get(prefix) ?? 0) + d.size_bytes);
  }

  const ranked = [...byPrefix.entries()]
    .map(([label, bytes]) => ({ label, bytes }))
    .sort((a, b) => b.bytes - a.bytes);

  const main: CategorySegment[] = [];
  let otherBytes = 0;

  for (const item of ranked) {
    const pct = (item.bytes / totalBytes) * 100;
    if (pct < MIN_SEGMENT_PCT && main.length > 0) {
      otherBytes += item.bytes;
    } else {
      main.push({
        label: item.label,
        bytes: item.bytes,
        color: CATEGORY_COLORS[main.length % CATEGORY_COLORS.length],
      });
    }
  }

  if (otherBytes > 0) {
    main.push({ label: "other", bytes: otherBytes, color: OTHER_COLOR });
  }

  return main;
}

export function largestCategory(
  segments: CategorySegment[],
  totalBytes: number,
): { label: string; pct: number } | null {
  if (totalBytes === 0 || segments.length === 0) return null;
  const top = segments[0];
  return { label: top.label, pct: (top.bytes / totalBytes) * 100 };
}
