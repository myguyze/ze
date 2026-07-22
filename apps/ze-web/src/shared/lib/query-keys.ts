import type { UiManifest } from "@/entities/ui-manifest";

export const queryKeys = {
  goals: ["goals"] as const,
  goalDetail: (goalId: string) => ["goal-detail", goalId] as const,
  goalTraces: (goalId: string, milestoneId?: string) =>
    ["goal-traces", goalId, milestoneId ?? ""] as const,
  workflows: ["workflows"] as const,
  workflowDetail: (workflowId: string) => ["workflow-detail", workflowId] as const,
  workflowExecutions: (workflowId: string) => ["workflow-executions", workflowId] as const,
  workflowRevisions: (workflowId: string) => ["workflow-revisions", workflowId] as const,
  costs: ["costs"] as const,
  costAnomalies: ["cost-anomalies"] as const,
  sessions: ["sessions"] as const,
  sessionSearch: (query: string) => ["sessions", "search", query] as const,
  uiManifest: ["ui-manifest"] as const,
  memoryFeed: (type: string, agent?: string, asOf?: string) => ["memory-feed", type, agent ?? "", asOf ?? ""] as const,
  messageTrace: (messageId: string) => ["message-trace", messageId] as const,
  messageTraces: (threadId: string, idsKey: string) =>
    ["message-traces", threadId, idsKey] as const,
  activityHeatmap: (start?: string, end?: string) => ["activity-heatmap", start ?? "", end ?? ""] as const,
  memoryGraph: (entityType?: string, seedId?: string) => ["memory-graph", entityType ?? "", seedId ?? ""] as const,
  entityDetail: (entityId: string) => ["entity-detail", entityId] as const,
  pluginPage: (path: string) => ["plugin-page", path] as const,
  pluginSettings: (id: string) => ["plugin-settings", id] as const,
  dataDomains: () => ["data-domains"] as const,
  notifications: (unreadOnly: boolean) => ["notifications", unreadOnly] as const,
  unreadNotificationCount: ["unread-notification-count"] as const,
  loops: (state?: string) => ["loops", state ?? ""] as const,
  loopDetail: (loopId: string) => ["loop-detail", loopId] as const,
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
