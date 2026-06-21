import { client as _defaultClient } from "./generated/client.gen";
import { createClient } from "./generated/client/client.gen";
import { createConfig } from "./generated/client/utils.gen";
import type { Client } from "./generated/client/types.gen";

export type { Client };

/**
 * Configure the default Ze API client.
 *
 * Call once at app startup — all SDK functions (listContacts, listGoals, etc.)
 * use this config automatically without needing `{ client }` passed per-call.
 *
 * ```ts
 * import { configure } from "@ze/client";
 * configure({ serverUrl: "http://localhost:8000", apiKey: "..." });
 *
 * // then just call functions directly
 * const { data } = await listContacts();
 * ```
 */
export function configure(options: { serverUrl: string; apiKey: string }): void {
  const base = options.serverUrl.replace(/\/$/, "");
  _defaultClient.setConfig(
    createConfig({
      baseUrl: base,
      headers: { Authorization: `Bearer ${options.apiKey}` },
    }),
  );
}

/**
 * Create an independent Ze API client (for multi-server or testing scenarios).
 *
 * ```ts
 * const { client } = createZeClient({ serverUrl, apiKey });
 * const { data } = await listContacts({ client });
 * ```
 */
export function createZeClient(options: { serverUrl: string; apiKey: string }): {
  client: Client;
} {
  const base = options.serverUrl.replace(/\/$/, "");
  const c = createClient(
    createConfig({
      baseUrl: base,
      headers: { Authorization: `Bearer ${options.apiKey}` },
    }),
  );
  return { client: c };
}
