export const queryKeys = {
  goals: ["goals"] as const,
  reminders: ["reminders"] as const,
  contacts: ["contacts"] as const,
  costs: ["costs"] as const,
  news: ["news"] as const,
  sessions: ["sessions"] as const,
  uiManifest: ["ui-manifest"] as const,
  pluginPage: (path: string) => ["plugin-page", path] as const,
};

const REFRESH_SCREEN_MAP: Record<string, readonly string[]> = {
  goals: queryKeys.goals,
  reminders: queryKeys.reminders,
  contacts: queryKeys.contacts,
  costs: queryKeys.costs,
};

export function refreshKeysForScreen(screen: string): readonly string[] | undefined {
  return REFRESH_SCREEN_MAP[screen];
}
