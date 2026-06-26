import type { HeatmapDay } from "@ze/client";
import { AGENT_COLORS, AGENT_COLOR_FALLBACK } from "@/shared/config";

interface Props {
  day: HeatmapDay;
}

function formatDate(isoDate: string): string {
  const d = new Date(isoDate + "T00:00:00");
  return d.toLocaleDateString("en-US", { weekday: "long", day: "numeric", month: "short" });
}

export function DayDetailPopover({ day }: Props) {
  const maxCount = Math.max(...day.agents.map((a) => a.count), 1);

  return (
    <div className="min-w-[180px] space-y-2">
      <p className="text-xs font-semibold text-white">{formatDate(day.date)}</p>
      <div className="border-t border-white/10" />
      <div className="space-y-1.5">
        {day.agents.map((a) => (
          <div key={a.agent} className="flex items-center gap-2">
            <span className="text-xs text-smoke capitalize w-20 truncate">{a.agent}</span>
            <div className="flex-1 h-2 rounded-full bg-white/5 overflow-hidden">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${(a.count / maxCount) * 100}%`,
                  backgroundColor: AGENT_COLORS[a.agent] ?? AGENT_COLOR_FALLBACK,
                }}
              />
            </div>
            <span className="text-xs text-smoke w-4 text-right">{a.count}</span>
          </div>
        ))}
      </div>
      <div className="border-t border-white/10" />
      <p className="text-xs text-smoke">Total: {day.total} messages</p>
    </div>
  );
}
