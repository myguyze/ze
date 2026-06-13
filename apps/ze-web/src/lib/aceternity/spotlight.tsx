import React, { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";

export function Spotlight({ className, children }: { className?: string; children?: React.ReactNode }) {
  const divRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [opacity, setOpacity] = useState(0);

  useEffect(() => {
    function handleMouseMove(e: MouseEvent) {
      if (!divRef.current) return;
      const rect = divRef.current.getBoundingClientRect();
      setPosition({ x: e.clientX - rect.left, y: e.clientY - rect.top });
      setOpacity(1);
    }
    function handleMouseLeave() {
      setOpacity(0);
    }

    const el = divRef.current;
    el?.addEventListener("mousemove", handleMouseMove);
    el?.addEventListener("mouseleave", handleMouseLeave);
    return () => {
      el?.removeEventListener("mousemove", handleMouseMove);
      el?.removeEventListener("mouseleave", handleMouseLeave);
    };
  }, []);

  return (
    <div ref={divRef} className={cn("relative overflow-hidden", className)}>
      <div
        className="pointer-events-none absolute inset-0 transition-opacity duration-300"
        style={{
          opacity,
          background: `radial-gradient(600px circle at ${position.x}px ${position.y}px, rgba(128,82,255,0.12), transparent 40%)`,
        }}
      />
      {children}
    </div>
  );
}
