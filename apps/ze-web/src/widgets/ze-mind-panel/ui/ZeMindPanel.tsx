import { Loader2 } from "lucide-react";
import { useCallback, useEffect, useRef } from "react";
import { useMindStore, useTraceSocket } from "@/features/ze-mind-state";
import { MindEmptyState } from "./EmptyState";
import { TraceEntry } from "./TraceEntry";

export function ZeMindPanel() {
  useTraceSocket();

  const open = useMindStore((s) => s.open);
  const width = useMindStore((s) => s.width);
  const traces = useMindStore((s) => s.traces);
  const pending = useMindStore((s) => s.pending);
  const setWidth = useMindStore((s) => s.setWidth);

  const dragging = useRef(false);
  const startX = useRef(0);
  const startWidth = useRef(0);
  const bottomRef = useRef<HTMLDivElement>(null);

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      dragging.current = true;
      startX.current = e.clientX;
      startWidth.current = width;
      e.preventDefault();
    },
    [width],
  );

  useEffect(() => {
    function onMouseMove(e: MouseEvent) {
      if (!dragging.current) return;
      const delta = startX.current - e.clientX;
      setWidth(startWidth.current + delta);
    }
    function onMouseUp() {
      dragging.current = false;
    }
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [setWidth]);

  // scroll to bottom when a new trace entry arrives
  useEffect(() => {
    if (traces.length > 0) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [traces.length]);

  if (!open) return null;

  return (
    <div
      className="hidden md:flex flex-col flex-shrink-0 border-l border-white/10 bg-black/20 relative overflow-hidden"
      style={{ width }}
    >
      {/* drag handle */}
      <div
        onMouseDown={onMouseDown}
        className="absolute left-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-plum-voltage/40 transition-colors z-10"
      />

      <div className="px-3 py-2.5 border-b border-white/[0.06] flex-shrink-0 flex items-center justify-between">
        <p className="text-xs font-medium text-smoke">Ze's Mind</p>
        {traces.length > 0 && (
          <span className="text-[10px] text-smoke/40">{traces.length} turn{traces.length !== 1 ? "s" : ""}</span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto relative">
        {traces.length === 0 && !pending ? (
          <MindEmptyState />
        ) : (
          <div className="text-xs">
            {traces.map((trace, i) => (
              <TraceEntry
                key={trace.message_id}
                trace={trace}
                index={i}
                defaultOpen={i === traces.length - 1}
              />
            ))}
            <div ref={bottomRef} />
          </div>
        )}

        {pending && (
          <div className="sticky bottom-0 flex items-center gap-2 px-3 py-2 bg-black/60 border-t border-white/[0.06] text-xs text-smoke">
            <Loader2 className="w-3 h-3 animate-spin flex-shrink-0" />
            Ze is thinking…
          </div>
        )}
      </div>
    </div>
  );
}
