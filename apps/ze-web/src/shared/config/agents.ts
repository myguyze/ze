export const AGENT_COLORS: Record<string, string> = {
  companion: "#3b82f6",
  research: "#f59e0b",
  calendar: "#10b981",
  messenger: "#8b5cf6",
  workflow: "#06b6d4",
  prospecting: "#ef4444",
};

export const AGENT_COLOR_FALLBACK = "#6b7280";

export function agentColor(agent: string): string {
  return AGENT_COLORS[agent] ?? AGENT_COLOR_FALLBACK;
}
