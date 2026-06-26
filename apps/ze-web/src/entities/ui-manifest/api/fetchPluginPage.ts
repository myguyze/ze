import { getConfig } from "@/shared/config";
import type { PluginPageResponse } from "../model/types";

export async function fetchPluginPage(path: string): Promise<PluginPageResponse> {
  const cfg = getConfig();
  if (!cfg) {
    throw new Error("App is not configured");
  }
  const base = cfg.serverUrl.replace(/\/$/, "");
  const res = await fetch(`${base}/api/v0/${path}/page`, {
    headers: { Authorization: `Bearer ${cfg.apiKey}` },
  });
  if (!res.ok) {
    throw new Error(`Failed to load plugin page: ${path}`);
  }
  return res.json() as Promise<PluginPageResponse>;
}
