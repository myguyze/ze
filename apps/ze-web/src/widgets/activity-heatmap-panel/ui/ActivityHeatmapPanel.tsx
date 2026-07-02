import { useState } from "react";
import { Activity } from "lucide-react";
import { useActivityHeatmapQuery } from "@/entities/activity";
import { AgentHeatmap, HeatmapLegend } from "@/widgets/agent-heatmap";
import { DashboardSectionTitle, EmptyState, ErrorState } from "@/shared/ui";

type Preset = "3M" | "6M" | "12M" | "YTD" | "custom";

const PRESETS: Exclude<Preset, "custom">[] = ["3M", "6M", "12M", "YTD"];

function presetDates(preset: Preset): { start: string; end: string } | null {
  if (preset === "custom") return null;
  const today = new Date();
  const end = today.toISOString().slice(0, 10);
  let start: Date;

  if (preset === "3M") {
    start = new Date(today);
    start.setMonth(today.getMonth() - 3);
  } else if (preset === "6M") {
    start = new Date(today);
    start.setMonth(today.getMonth() - 6);
  } else if (preset === "YTD") {
    start = new Date(today.getFullYear(), 0, 1);
  } else {
    start = new Date(today);
    start.setFullYear(today.getFullYear() - 1);
  }

  return { start: start.toISOString().slice(0, 10), end };
}

export function ActivityHeatmapPanel() {
  const [preset, setPreset] = useState<Preset>("12M");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");

  const dates = preset === "custom"
    ? (customStart && customEnd ? { start: customStart, end: customEnd } : null)
    : presetDates(preset);

  const { data, isPending, isError } = useActivityHeatmapQuery(
    dates?.start,
    dates?.end,
  );

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <DashboardSectionTitle className="mb-1">Agent activity</DashboardSectionTitle>
          <p className="text-xs text-smoke/70">
            Daily message volume by agent
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1 rounded-lg border border-white/10 p-1">
            {PRESETS.map((p) => (
              <button
                key={p}
                onClick={() => setPreset(p)}
                className={`px-3 py-1 rounded text-xs transition-colors ${
                  preset === p
                    ? "bg-plum-voltage/20 text-white"
                    : "text-smoke hover:text-white"
                }`}
              >
                {p}
              </button>
            ))}
            <button
              onClick={() => setPreset("custom")}
              className={`px-3 py-1 rounded text-xs transition-colors ${
                preset === "custom"
                  ? "bg-plum-voltage/20 text-white"
                  : "text-smoke hover:text-white"
              }`}
            >
              Custom
            </button>
          </div>

          {preset === "custom" && (
            <div className="flex items-center gap-2">
              <input
                type="date"
                value={customStart}
                onChange={(e) => setCustomStart(e.target.value)}
                className="rounded border border-white/10 bg-transparent px-2 py-1 text-xs text-white focus:outline-none focus:border-plum-voltage [color-scheme:dark]"
              />
              <span className="text-xs text-smoke">–</span>
              <input
                type="date"
                value={customEnd}
                min={customStart || undefined}
                onChange={(e) => setCustomEnd(e.target.value)}
                className="rounded border border-white/10 bg-transparent px-2 py-1 text-xs text-white focus:outline-none focus:border-plum-voltage [color-scheme:dark]"
              />
            </div>
          )}
        </div>
      </div>

      {preset === "custom" && (!customStart || !customEnd) && (
        <p className="text-sm text-smoke">Select a start and end date to view activity.</p>
      )}

      {isPending && dates && (
        <div className="h-40 flex items-center justify-center text-sm text-smoke">
          Loading…
        </div>
      )}

      {isError && <ErrorState message="Could not load activity data." />}

      {data && data.days.length === 0 && (
        <EmptyState
          icon={Activity}
          message="No activity in this period."
          detail="Start chatting with Ze to see your usage patterns here."
        />
      )}

      {data && data.days.length > 0 && (
        <div className="space-y-4">
          <div className="overflow-x-auto">
            <AgentHeatmap data={data} />
          </div>
          <HeatmapLegend agents={data.agents} />
        </div>
      )}
    </section>
  );
}
