import { ChevronDown } from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";
import { cn } from "@/shared/lib/cn";

interface BreakdownGroupProps {
  title: ReactNode;
  summary?: ReactNode;
  collapsedHint?: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
}

export function BreakdownGroup({
  title,
  summary,
  collapsedHint,
  children,
  defaultOpen = true,
}: BreakdownGroupProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="border-b border-white/[0.06] last:border-0 pb-4 last:pb-0">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 py-1 text-left group"
      >
        <span className="text-[10px] font-semibold tracking-widest uppercase text-smoke/80 group-hover:text-smoke transition-colors">
          {title}
        </span>
        <div className="flex items-center gap-2 flex-shrink-0">
          {summary && (
            <span className="text-[10px] text-smoke/80 tabular-nums">{summary}</span>
          )}
          <ChevronDown
            className={cn(
              "w-3.5 h-3.5 text-smoke transition-transform",
              open && "rotate-180",
            )}
          />
        </div>
      </button>

      {open && <div className="mt-3 space-y-2">{children}</div>}

      {!open && collapsedHint && (
        <p className="mt-1 text-[9px] text-smoke/80 tabular-nums">{collapsedHint}</p>
      )}
    </div>
  );
}
