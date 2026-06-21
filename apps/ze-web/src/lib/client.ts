import { configure, ApiError } from "@ze/client";
import { getConfig } from "@/config/AppConfig";

export { ApiError };

export function applyConfig(): void {
  const cfg = getConfig();
  if (cfg) configure({ serverUrl: cfg.serverUrl, apiKey: cfg.apiKey });
}

/** Call after saving new config so the next request uses updated credentials. */
export function resetClient(): void {
  applyConfig();
}
