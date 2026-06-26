import { AGENT_COLORS, AGENT_COLOR_FALLBACK } from "@/shared/config";

interface Props {
  agents: string[];
}

export function HeatmapLegend({ agents }: Props) {
  if (agents.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-x-4 gap-y-2">
      {agents.map((agent) => (
        <div key={agent} className="flex items-center gap-1.5">
          <span
            className="h-3 w-3 rounded-sm flex-shrink-0"
            style={{ backgroundColor: AGENT_COLORS[agent] ?? AGENT_COLOR_FALLBACK }}
          />
          <span className="text-xs text-smoke capitalize">{agent}</span>
        </div>
      ))}
    </div>
  );
}
