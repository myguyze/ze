import { getConfig } from "@/shared/config";
import type { UiManifest } from "../model/types";

export async function fetchUiManifest(): Promise<UiManifest> {
  const cfg = getConfig();
  if (!cfg) {
    return { nav: [], settings_sections: [] };
  }
  const base = cfg.serverUrl.replace(/\/$/, "");
  const res = await fetch(`${base}/api/v0/ui/manifest`, {
    headers: { Authorization: `Bearer ${cfg.apiKey}` },
  });
  if (!res.ok) {
    throw new Error("Failed to load UI manifest");
  }
  return res.json() as Promise<UiManifest>;
}
