interface TimelineScrubberProps {
  earliest: Date;
  value: Date | null;
  onChange: (d: Date | null) => void;
}

function formatDate(d: Date): string {
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function daysAgo(d: Date): number {
  return Math.floor((Date.now() - d.getTime()) / 86_400_000);
}

export function TimelineScrubber({ earliest, value, onChange }: TimelineScrubberProps) {
  const min = earliest.getTime();
  const max = Date.now();
  const sliderValue = value ? value.getTime() : max;

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const ms = Number(e.target.value);
    if (ms >= max - 60_000) {
      onChange(null);
    } else {
      onChange(new Date(ms));
    }
  }

  const ago = value ? daysAgo(value) : 0;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs text-smoke">
        <span>{formatDate(earliest)}</span>
        {value ? (
          <span className="font-medium text-warning">{formatDate(value)} — {ago} day{ago !== 1 ? "s" : ""} ago</span>
        ) : (
          <span className="text-white/50">Now</span>
        )}
        <span>Today</span>
      </div>

      <div className="flex items-center gap-3">
        <input
          type="range"
          min={min}
          max={max}
          value={sliderValue}
          step={86_400_000}
          onChange={handleChange}
          className="flex-1 h-1.5 rounded-full accent-plum-voltage cursor-pointer"
        />
        {value && (
          <button
            onClick={() => onChange(null)}
            className="shrink-0 px-2 py-0.5 rounded text-xs border border-white/10 text-smoke hover:text-white hover:border-white/30 transition-colors"
          >
            Now
          </button>
        )}
      </div>
    </div>
  );
}
