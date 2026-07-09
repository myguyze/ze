import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { cn, motion } from "@/shared/lib";

interface SidePanelProps {
  open: boolean;
  width: number;
  onWidthChange: (width: number) => void;
  onClose: () => void;
  header: ReactNode;
  children: ReactNode;
  className?: string;
}

function useMinMd() {
  const [minMd, setMinMd] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(min-width: 768px)").matches,
  );

  useEffect(() => {
    const mq = window.matchMedia("(min-width: 768px)");
    const onChange = () => setMinMd(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  return minMd;
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
  const isDesktop = useMinMd();
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

  const panelBody = (
    <>
      <div
        onMouseDown={onMouseDown}
        className={cn(
          "absolute left-0 top-0 bottom-0 z-10 hidden w-1 cursor-col-resize hover:bg-plum-voltage/40 md:block",
          motion.colors,
        )}
      />
      {header}
      <div className="relative min-h-0 flex-1 overflow-hidden">{children}</div>
    </>
  );

  if (isDesktop) {
    return (
      <div
        className={cn(
          "flex-shrink-0 overflow-hidden",
          motion.base,
          !open && "pointer-events-none",
        )}
        style={{ width: open ? width : 0, opacity: open ? 1 : 0 }}
        aria-hidden={!open}
      >
        <aside
          className={cn(
            "relative flex h-full flex-col overflow-hidden border-l border-white/10 bg-black/20",
            className,
          )}
          style={{ width }}
        >
          {panelBody}
        </aside>
      </div>
    );
  }

  return (
    <>
      <button
        type="button"
        aria-label="Close panel"
        onClick={onClose}
        aria-hidden={!open}
        tabIndex={open ? 0 : -1}
        className={cn(
          "fixed inset-0 z-40 bg-black/60",
          motion.fade,
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
      />
      <aside
        aria-hidden={!open}
        className={cn(
          "fixed inset-y-0 right-0 z-50 flex flex-col overflow-hidden border-l border-white/10 bg-black/20",
          motion.slide,
          open ? "translate-x-0 opacity-100" : "pointer-events-none translate-x-full opacity-0",
          className,
        )}
        style={{ width }}
      >
        {panelBody}
      </aside>
    </>
  );
}
