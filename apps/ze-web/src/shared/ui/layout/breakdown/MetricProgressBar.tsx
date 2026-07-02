interface MetricProgressBarProps {
  pct: number;
  minWidthPct?: number;
}

export function MetricProgressBar({ pct, minWidthPct = 0.5 }: MetricProgressBarProps) {
  return (
    <div className="relative h-[3px] rounded-full bg-white/[0.06] overflow-hidden">
      <div
        className="absolute inset-y-0 left-0 bg-plum-voltage rounded-full transition-all duration-500"
        style={{ width: `${Math.max(pct, minWidthPct)}%` }}
      />
    </div>
  );
}
