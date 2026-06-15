const REFRESH_QUERY_KEYS: Record<string, readonly string[]> = {
  goals: ["goals"],
  reminders: ["reminders"],
  contacts: ["contacts"],
  costs: ["costs"],
  news: ["news"],
};

export function queryKeysForRefreshScreen(screen: string): readonly string[] | undefined {
  return REFRESH_QUERY_KEYS[screen];
}
