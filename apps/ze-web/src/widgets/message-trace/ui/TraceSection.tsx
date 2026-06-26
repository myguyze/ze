import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

interface TraceSectionProps {
  title: string;
  count?: number;
  children: React.ReactNode;
  defaultOpen?: boolean;
}

export function TraceSection({ title, count, children, defaultOpen = true }: TraceSectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="border-t border-white/[0.06] first:border-t-0">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 w-full px-3 py-2 text-xs text-smoke hover:text-white transition-colors text-left"
      >
        {open ? (
          <ChevronDown className="w-3 h-3 flex-shrink-0" />
        ) : (
          <ChevronRight className="w-3 h-3 flex-shrink-0" />
        )}
        <span className="font-medium">
          {title}
          {count !== undefined && (
            <span className="ml-1 text-smoke/60">({count})</span>
          )}
        </span>
      </button>
      {open && <div className="px-3 pb-2">{children}</div>}
    </div>
  );
}
