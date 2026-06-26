import type { UiContribution } from "./types";

export function settingsSegment(entry: UiContribution): string {
  if (entry.path) {
    return entry.path;
  }
  return entry.plugin.replace(/^ze_/, "").replace(/_/g, "-");
}

export function settingsEndpoint(entry: UiContribution): string {
  return `/api/v0/${settingsSegment(entry)}/settings`;
}
