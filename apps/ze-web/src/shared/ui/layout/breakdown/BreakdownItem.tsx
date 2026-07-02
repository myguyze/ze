import { ChevronDown } from "lucide-react";
import { Children, type ReactNode } from "react";
import { useState } from "react";
import { cn } from "@/shared/lib/cn";

interface BreakdownItemProps {
  header: ReactNode;
  meta?: ReactNode;
  children?: ReactNode;
  defaultOpen?: boolean;
}

export function BreakdownItem({
  header,
  meta,
  children,
  defaultOpen = false,
}: BreakdownItemProps) {
  const expandable = Children.count(children) > 0;
  const [open, setOpen] = useState(defaultOpen);

  const headerClassName =
    "flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors";
  const interactiveClassName = expandable ? " hover:bg-white/[0.03]" : "";

  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] overflow-hidden">
      {expandable ? (
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
          className={cn(headerClassName, interactiveClassName)}
        >
          <div className="flex-1 min-w-0">{header}</div>
          <div className="flex items-center gap-2 flex-shrink-0 text-[10px] tabular-nums">
            {meta}
            <ChevronDown
              className={cn(
                "w-3.5 h-3.5 text-smoke transition-transform",
                open && "rotate-180",
              )}
            />
          </div>
        </button>
      ) : (
        <div className={headerClassName}>
          <div className="flex-1 min-w-0">{header}</div>
          {meta && (
            <div className="flex items-center gap-2 flex-shrink-0 text-[10px] tabular-nums">
              {meta}
            </div>
          )}
        </div>
      )}

      {expandable && open && (
        <div className="px-3 pb-3 border-t border-white/[0.06] pt-2.5">{children}</div>
      )}
    </div>
  );
}
