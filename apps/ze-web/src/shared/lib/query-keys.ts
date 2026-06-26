import type { UiManifest } from "@/entities/ui-manifest";

export const queryKeys = {
  goals: ["goals"] as const,
  workflows: ["workflows"] as const,
  costs: ["costs"] as const,
  sessions: ["sessions"] as const,
  uiManifest: ["ui-manifest"] as const,
  memoryFeed: (type: string, agent?: string) => ["memory-feed", type, agent ?? ""] as const,
  pluginPage: (path: string) => ["plugin-page", path] as const,
  pluginSettings: (id: string) => ["plugin-settings", id] as const,
};

const CORE_REFRESH_SCREEN_MAP: Record<string, readonly string[]> = {
  goals: queryKeys.goals,
  workflows: queryKeys.workflows,
  costs: queryKeys.costs,
};

export function refreshKeysForScreen(
  screen: string,
  manifest?: UiManifest | null,
): readonly string[] | undefined {
  const coreKeys = CORE_REFRESH_SCREEN_MAP[screen];
  if (coreKeys) {
    return coreKeys;
  }

  const pluginEntry = manifest?.nav.find((item) => item.path === screen);
  if (pluginEntry) {
    return queryKeys.pluginPage(pluginEntry.id);
  }

  return undefined;
}
