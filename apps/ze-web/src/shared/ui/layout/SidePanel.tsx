import { useCallback, useEffect, useRef, type ReactNode } from "react";
import { cn } from "@/shared/lib/cn";

interface SidePanelProps {
  open: boolean;
  width: number;
  onWidthChange: (width: number) => void;
  onClose: () => void;
  header: ReactNode;
  children: ReactNode;
  className?: string;
}

export function SidePanel({
  open,
  width,
  onWidthChange,
  onClose,
  header,
  children,
  className,
}: SidePanelProps) {
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
      onWidthChange(startWidth.current + delta);
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
  }, [onWidthChange]);

  if (!open) return null;

  return (
    <>
      <button
        type="button"
        aria-label="Close panel"
        onClick={onClose}
        className="md:hidden fixed inset-0 z-40 bg-black/60"
      />
      <aside
        className={cn(
          "flex flex-col flex-shrink-0 border-l border-white/10 bg-black/20 relative overflow-hidden z-50",
          "fixed inset-y-0 right-0 md:relative md:inset-auto",
          className,
        )}
        style={{ width }}
      >
        <div
          onMouseDown={onMouseDown}
          className="absolute left-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-plum-voltage/40 transition-colors z-10 hidden md:block"
        />
        {header}
        <div className="flex-1 min-h-0 overflow-y-auto relative">{children}</div>
      </aside>
    </>
  );
}
