import { useEffect, useRef, useState, type HTMLAttributes, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { REDIRECT_HINT_DURATION_MS } from "@/shared/lib/redirect-hint";
import { cn } from "@/shared/lib/cn";

type RedirectHintTargetProps = HTMLAttributes<HTMLDivElement> & {
  hintId: string;
  children: ReactNode;
};

/**
 * Wraps a screen region that can be scrolled to and briefly highlighted when
 * the user arrives via `redirectHintPath("/screen", hintId)`.
 */
export function RedirectHintTarget({
  hintId,
  children,
  className,
  ...props
}: RedirectHintTargetProps) {
  const location = useLocation();
  const targetRef = useRef<HTMLDivElement>(null);
  const [hintActive, setHintActive] = useState(false);

  useEffect(() => {
    if (location.hash !== `#${hintId}`) return;

    const el = targetRef.current;
    if (!el) return;

    const frame = requestAnimationFrame(() => {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    });

    setHintActive(true);
    const timer = window.setTimeout(() => setHintActive(false), REDIRECT_HINT_DURATION_MS);

    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(timer);
    };
  }, [location.hash, hintId]);

  return (
    <div
      ref={targetRef}
      id={hintId}
      className={cn(
        "scroll-mt-8 rounded-2xl transition-[box-shadow,background-color] duration-700",
        hintActive &&
          "ring-2 ring-plum-voltage/60 bg-plum-voltage/[0.08] shadow-[0_0_24px_rgba(128,82,255,0.12)]",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}
