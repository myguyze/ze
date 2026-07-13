import { useEffect, useMemo, useState } from "react";
import { History } from "lucide-react";
import { Button, Slider } from "@/shared/ui";

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
// Radix insets the thumb's center by half its own rendered width as it nears
// either track edge (so it never overhangs the track) — see
// getThumbInBoundsOffset in @radix-ui/react-slider. The floating date pill
// is a separate overlay, not part of the thumb itself, so it has to
// reproduce that same offset to stay glued to the thumb's real position.
// The playhead line itself doesn't need this: it's rendered as the thumb's
// own content (see `thumbChildren` below), so it's physically the same
// element Radix is positioning and can never drift from it.
const THUMB_PX = 2;

function thumbPositionStyle(percent: number): string {
  const halfWidth = THUMB_PX / 2;
  const offsetPx = halfWidth - (percent / 50) * halfWidth;
  return `calc(${percent}% + ${offsetPx}px)`;
}

function formatDate(d: Date): string {
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function formatDateShort(d: Date): string {
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function dayIndex(ms: number, min: number): number {
  return Math.floor((ms - min) / DAY_MS);
}

function agoLabel(days: number): string {
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
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
  const pillLeft = thumbPositionStyle(percent);
  const liveLabel = isNow ? "Live" : formatDate(liveDate);
  const isSnapshot = value !== null;
  // Only surface the floating pill while it's telling the user something new —
  // mid-drag feedback, or "you're viewing a past snapshot". At rest on Now,
  // it just repeats what "Today" already says below the track.
  const showLabel = dragging || !isNow;

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-semibold tracking-widest uppercase text-smoke">
          Memory Timeline
        </span>
        <Button
          variant={isSnapshot ? "amber" : "ghost"}
          onClick={() => onChange(null)}
          disabled={!isSnapshot}
          className="h-6 gap-1 px-2 text-[10px]"
        >
          <History className="size-2.5" />
          Jump to now
        </Button>
      </div>

      <div className="relative pt-2">
        {/* Activity waveform doubles as the track — bars past the selected
            point are dimmed to read as "not yet part of this snapshot". The
            thumb is rendered as a full-height line with a small grip knob
            (via `thumbChildren`) instead of a free-floating dot, so the
            handle and the line are the same element and can't drift apart. */}
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
          thumbAriaValueText={isNow ? "Live" : `${formatDate(liveDate)}, ${agoLabel(todayIndex - liveDayIndex)}`}
          trackClassName="h-12 bg-transparent"
          thumbClassName="group h-12 w-0.5 shrink-0 rounded-none bg-white/25 shadow-none transition-colors hover:bg-white/45 active:bg-white/60 hover:scale-100 active:scale-100 active:shadow-none"
          thumbChildren={
            <span className="pointer-events-none absolute left-1/2 top-0 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-plum-voltage shadow-[0_0_0_3px_rgba(0,0,0,0.7)] transition-transform duration-150 group-hover:scale-110 group-active:scale-125" />
          }
        >
          {buckets.length > 0 && (
            <div className="pointer-events-none absolute inset-x-0 bottom-0 flex h-6 items-end gap-px">
              {buckets.map((count, i) => {
                const bucketStart = min + (i / buckets.length) * (max - min);
                const isFuture = bucketStart > liveMs + DAY_MS;
                const intensity = count > 0 ? 0.4 + 0.6 * (count / bucketMax) : 0.14;
                return (
                  <div
                    key={i}
                    className="flex-1 rounded-t-[1.5px] bg-plum-voltage transition-opacity"
                    style={{
                      height: `${Math.max(12, (count / bucketMax) * 100)}%`,
                      opacity: isFuture ? intensity * 0.3 : intensity,
                    }}
                  />
                );
              })}
            </div>
          )}
        </Slider>

        <div className="relative flex items-center justify-between pt-1.5 text-[11px] text-smoke/70">
          <span>{formatDateShort(earliest)}</span>
          {/* Current-position label — sits in the same row as the start/today
              bounds, styled the same way, instead of floating above the pin. */}
          {showLabel && (
            <span
              className={`pointer-events-none absolute top-1.5 whitespace-nowrap font-medium transition-[left,color] ${
                dragging ? "text-bone" : "text-warning"
              }`}
              style={{ left: pillLeft, transform: "translateX(-50%)" }}
            >
              {liveLabel}
            </span>
          )}
          <span>Today</span>
        </div>
      </div>
    </div>
  );
}
