import { getConfig } from "@/shared/config";
import type { PluginPageResponse } from "../model/types";
import { settingsEndpoint } from "../model/settings-endpoint";
import type { UiContribution } from "../model/types";

export async function fetchPluginSettings(entry: UiContribution): Promise<PluginPageResponse> {
  const cfg = getConfig();
  if (!cfg) {
    throw new Error("App is not configured");
  }
  const base = cfg.serverUrl.replace(/\/$/, "");
  const res = await fetch(`${base}${settingsEndpoint(entry)}`, {
    headers: { Authorization: `Bearer ${cfg.apiKey}` },
  });
  if (!res.ok) {
    throw new Error(`Failed to load settings: ${entry.id}`);
  }
  return res.json() as Promise<PluginPageResponse>;
}
