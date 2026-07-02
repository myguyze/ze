import { capitalize, formatBytes } from "../lib/format";
import type { CategorySegment } from "../lib/aggregate";

type StorageDonutChartProps = {
  segments: CategorySegment[];
  totalBytes: number;
};

export function StorageDonutChart({ segments, totalBytes }: StorageDonutChartProps) {
  if (totalBytes === 0 || segments.length === 0) {
    return (
      <div className="flex items-center gap-6">
        <div className="w-[140px] h-[140px] rounded-full border border-white/[0.08] bg-white/[0.02] flex items-center justify-center flex-shrink-0">
          <p className="text-[10px] text-smoke/50 uppercase tracking-widest">No data</p>
        </div>
        <p className="text-sm text-smoke">Storage will appear once domains have data.</p>
      </div>
    );
  }

  const R = 38;
  const stroke = 14;
  const C = 2 * Math.PI * R;
  let offset = 0;

  return (
    <div className="flex items-center gap-6">
      <div className="relative w-[140px] h-[140px] flex-shrink-0">
        <svg viewBox="0 0 100 100" className="w-full h-full" aria-hidden="true">
          <circle
            cx="50"
            cy="50"
            r={R}
            fill="none"
            stroke="rgba(255,255,255,0.05)"
            strokeWidth={stroke}
          />
          {segments.map((seg) => {
            const pct = seg.bytes / totalBytes;
            const dash = pct * C;
            const el = (
              <circle
                key={seg.label}
                cx="50"
                cy="50"
                r={R}
                fill="none"
                stroke={seg.color}
                strokeWidth={stroke}
                strokeDasharray={`${dash} ${C - dash}`}
                strokeDashoffset={-offset}
                transform="rotate(-90 50 50)"
                strokeLinecap="butt"
              />
            );
            offset += dash;
            return el;
          })}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <p className="text-sm font-light text-white tabular-nums">{segments.length}</p>
          <p className="text-[9px] text-smoke uppercase tracking-widest">groups</p>
        </div>
      </div>

      <div className="flex-1 space-y-2 min-w-0">
        {segments.map((seg) => {
          const pct = (seg.bytes / totalBytes) * 100;
          return (
            <div key={seg.label} className="flex items-center gap-2 min-w-0">
              <div
                className="w-2 h-2 rounded-full flex-shrink-0"
                style={{ backgroundColor: seg.color }}
              />
              <p className="text-xs text-white truncate flex-1">
                {capitalize(seg.label)}
              </p>
              <p className="text-[10px] text-smoke tabular-nums flex-shrink-0">
                {formatBytes(seg.bytes)}
              </p>
              <p className="text-[10px] text-smoke/60 tabular-nums w-10 text-right flex-shrink-0">
                {pct.toFixed(0)}%
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
