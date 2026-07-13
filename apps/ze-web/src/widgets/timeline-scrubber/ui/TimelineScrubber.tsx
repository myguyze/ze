import { useEffect, useMemo, useState } from "react";
import { Slider } from "@/shared/ui";

interface ActivityDay {
  date: string;
  count: number;
}

interface TimelineScrubberProps {
  earliest: Date;
  value: Date | null;
  onChange: (d: Date | null) => void;
  /** Per-day fact+episode counts across [earliest, now]. Rendered as the track's density waveform. */
  activity?: ActivityDay[];
  activityMax?: number;
}

const DAY_MS = 86_400_000;
const MAX_BUCKETS = 120;

function formatDate(d: Date): string {
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function dayIndex(ms: number, min: number): number {
  return Math.floor((ms - min) / DAY_MS);
}

function agoLabel(days: number): string {
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  return `${days} days ago`;
}

export function TimelineScrubber({ earliest, value, onChange, activity, activityMax }: TimelineScrubberProps) {
  const min = earliest.getTime();
  // Frozen for the component's lifetime — recomputing Date.now() on every
  // render (including the ones a drag triggers) made `committedMs` below
  // drift on each tick, so the sync effect kept snapping liveMs back to
  // "now" mid-drag and the thumb could never actually move away from Now.
  const max = useMemo(() => Date.now(), []);
  const todayIndex = dayIndex(max, min);
  const committedMs = value ? value.getTime() : max;

  // Live preview follows the thumb on every Radix `onValueChange` (continuous);
  // the parent (and its feed refetch) only hears about it via `onValueCommit`,
  // which fires once per drag gesture (pointer release) or per keyboard step —
  // not on every tick.
  const [liveMs, setLiveMs] = useState(committedMs);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    setLiveMs(committedMs);
  }, [committedMs]);

  // Bucket day-level activity into a fixed number of bars so the density graph
  // stays legible and cheap to render whether the history spans weeks or years.
  const buckets = useMemo(() => {
    const span = Math.max(1, max - min);
    const totalDays = todayIndex + 1;
    const numBuckets = Math.min(MAX_BUCKETS, totalDays);
    const bucketSpan = span / numBuckets;
    const counts = new Array(numBuckets).fill(0);
    for (const day of activity ?? []) {
      const t = new Date(`${day.date}T00:00:00Z`).getTime();
      if (Number.isNaN(t) || t < min || t > max) continue;
      const idx = Math.min(numBuckets - 1, Math.floor((t - min) / bucketSpan));
      counts[idx] += day.count;
    }
    return counts;
  }, [activity, min, max, todayIndex]);

  const bucketMax = Math.max(1, activityMax ?? 0, ...buckets);

  // Snap to "Now" (null) once the thumb reaches today's bucket — comparing by
  // calendar day, not exact epoch-ms, since the slider's day-sized step rarely
  // lands exactly on `max` and a naive ms comparison leaves it stuck one step short.
  function commit(ms: number) {
    setDragging(false);
    if (dayIndex(ms, min) >= todayIndex) {
      onChange(null);
    } else {
      onChange(new Date(ms));
    }
  }

  const liveDate = new Date(liveMs);
  const liveDayIndex = dayIndex(liveMs, min);
  const isNow = liveDayIndex >= todayIndex;
  const percent = ((liveMs - min) / (max - min)) * 100;
  // Clamp the label's own translation so it doesn't clip past the track edges
  // when the thumb sits near either end.
  const labelPercent = Math.min(94, Math.max(6, percent));
  const liveLabel = isNow ? "Now" : `${formatDate(liveDate)} — ${agoLabel(todayIndex - liveDayIndex)}`;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between text-xs text-smoke">
        <span>{formatDate(earliest)}</span>
        <span>Today</span>
      </div>

      <div className="flex items-center gap-3">
        <div className="relative flex-1 pt-6">
          {(dragging || !isNow) && (
            <div
              className={`pointer-events-none absolute top-0 whitespace-nowrap text-xs font-medium transition-[left] ${
                dragging ? "text-bone" : "text-warning"
              }`}
              style={{ left: `${labelPercent}%`, transform: "translateX(-50%)" }}
            >
              {liveLabel}
            </div>
          )}

          {/* Activity waveform doubles as the track — bars past the selected
              point are dimmed to read as "not yet part of this snapshot". */}
          <div className="py-2.5">
            <Slider
              min={min}
              max={max}
              step={DAY_MS}
              value={[liveMs]}
              onValueChange={([v]) => {
                setDragging(true);
                setLiveMs(v);
              }}
              onValueCommit={([v]) => commit(v)}
              thumbAriaLabel="Memory timeline position"
              thumbAriaValueText={liveLabel}
              trackClassName="h-5 bg-transparent"
            >
              {buckets.length > 0 && (
                <div className="pointer-events-none absolute inset-x-0 bottom-0 flex h-5 items-end gap-px">
                  {buckets.map((count, i) => {
                    const bucketStart = min + (i / buckets.length) * (max - min);
                    const isFuture = bucketStart > liveMs + DAY_MS;
                    const intensity = count > 0 ? 0.35 + 0.55 * (count / bucketMax) : 0.12;
                    return (
                      <div
                        key={i}
                        className="flex-1 rounded-t-[1px] bg-plum-voltage transition-opacity"
                        style={{
                          height: `${Math.max(10, (count / bucketMax) * 100)}%`,
                          opacity: isFuture ? intensity * 0.3 : intensity,
                        }}
                      />
                    );
                  })}
                </div>
              )}
            </Slider>
          </div>
        </div>
        <button
          onClick={() => onChange(null)}
          disabled={!value}
          className={`shrink-0 w-14 px-2 py-0.5 rounded text-xs border transition-colors ${
            value
              ? "border-white/10 text-smoke hover:text-white hover:border-white/30"
              : "border-transparent text-transparent pointer-events-none"
          }`}
        >
          Now
        </button>
      </div>
    </div>
  );
}
