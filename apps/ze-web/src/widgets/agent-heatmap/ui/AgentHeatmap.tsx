import { useState, useRef } from "react";
import HeatMap, { type HeatMapValue } from "@uiw/react-heat-map";
import type { ActivityHeatmapResponse, HeatmapDay } from "@ze/client";
import { agentColor } from "@/shared/config";
import { DayDetailPopover } from "./DayDetailPopover";

interface Props {
  data: ActivityHeatmapResponse;
}

function dominantColor(day: HeatmapDay): string {
  if (day.agents.length === 0) return "#6b7280";
  return agentColor(day.agents[0].agent);
}

function intensityAlpha(total: number): number {
  if (total <= 0) return 0;
  if (total <= 2) return 0.3;
  if (total <= 5) return 0.6;
  return 1;
}

export function AgentHeatmap({ data }: Props) {
  const [hoveredDay, setHoveredDay] = useState<HeatmapDay | null>(null);
  const [popoverPos, setPopoverPos] = useState({ x: 0, y: 0 });
  const containerRef = useRef<HTMLDivElement>(null);

  const dayMap = new Map<string, HeatmapDay>(data.days.map((d) => [d.date, d]));

  const values: HeatMapValue[] = data.days.map((d) => ({
    date: d.date,
    count: d.total,
  }));

  const startDate = new Date(data.start + "T00:00:00");
  const endDate = new Date(data.end + "T00:00:00");

  return (
    <div ref={containerRef} className="relative">
      <HeatMap
        value={values}
        startDate={startDate}
        endDate={endDate}
        rectSize={14}
        space={3}
        weekLabels={["", "Mon", "", "Wed", "", "Fri", ""]}
        style={{ color: "#6b7280" }}
        rectRender={(rectProps, item) => {
          const day = dayMap.get(item.date);
          const color = day ? dominantColor(day) : "#374151";
          const alpha = day ? intensityAlpha(item.count) : 0;

          return (
            <rect
              {...rectProps}
              rx={2}
              fill={alpha === 0 ? "#1f2937" : color}
              opacity={alpha === 0 ? 1 : alpha}
              style={{ cursor: day ? "pointer" : "default" }}
              onMouseEnter={(e) => {
                if (!day) return;
                const rect = containerRef.current?.getBoundingClientRect();
                const target = e.currentTarget.getBoundingClientRect();
                setPopoverPos({
                  x: target.left - (rect?.left ?? 0) + target.width / 2,
                  y: target.top - (rect?.top ?? 0),
                });
                setHoveredDay(day);
              }}
              onMouseLeave={() => setHoveredDay(null)}
            />
          );
        }}
      />

      {hoveredDay && (
        <div
          className="absolute z-50 bg-[#111827] border border-white/10 rounded-lg p-3 shadow-xl pointer-events-none"
          style={{
            left: popoverPos.x,
            top: popoverPos.y - 8,
            transform: "translate(-50%, -100%)",
          }}
        >
          <DayDetailPopover day={hoveredDay} />
        </div>
      )}
    </div>
  );
}
