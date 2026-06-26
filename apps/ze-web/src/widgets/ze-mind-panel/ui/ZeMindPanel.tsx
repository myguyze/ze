import { Loader2 } from "lucide-react";
import { useCallback, useEffect, useRef } from "react";
import { useMindStore, useTraceSocket } from "@/features/ze-mind-state";
import { MindEmptyState } from "./EmptyState";
import { MemorySection } from "./MemorySection";
import { RoutingSection } from "./RoutingSection";
import { ToolsSection } from "./ToolsSection";

export function ZeMindPanel() {
  useTraceSocket();

  const open = useMindStore((s) => s.open);
  const width = useMindStore((s) => s.width);
  const trace = useMindStore((s) => s.trace);
  const pending = useMindStore((s) => s.pending);
  const setWidth = useMindStore((s) => s.setWidth);

  const dragging = useRef(false);
  const startX = useRef(0);
  const startWidth = useRef(0);

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

      <div className="px-3 py-2.5 border-b border-white/[0.06] flex-shrink-0">
        <p className="text-xs font-medium text-smoke">Ze's Mind</p>
      </div>

      <div className="flex-1 overflow-y-auto relative">
        {pending && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/40 z-10">
            <div className="flex items-center gap-2 text-xs text-smoke">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Ze is thinking…
            </div>
          </div>
        )}

        {!trace ? (
          <MindEmptyState />
        ) : (
          <div className="rounded-none border-none text-xs">
            <RoutingSection trace={trace} />
            <MemorySection chunks={trace.memory_chunks} />
            <ToolsSection toolCalls={trace.tool_calls} />
          </div>
        )}
      </div>
    </div>
  );
}
