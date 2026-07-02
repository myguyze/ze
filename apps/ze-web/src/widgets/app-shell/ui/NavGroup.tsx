import { ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/shared/lib/cn";
import { motion } from "@/shared/lib/motion";

interface NavGroupProps {
  icon: LucideIcon;
  label: string;
  children: React.ReactNode;
  /** If set, the label area is a NavLink to this path */
  href?: string;
  hrefIndex?: boolean;
  /** Route paths (without leading slash) that auto-open this group when active */
  childPaths?: string[];
  defaultOpen?: boolean;
  /** Aggregate child status shown as an indicator when the group is collapsed */
  status?: "thinking" | "attention" | null;
}

export function NavGroup({
  icon: Icon,
  label,
  children,
  href,
  hrefIndex,
  childPaths = [],
  defaultOpen = false,
  status,
}: NavGroupProps) {
  const { pathname } = useLocation();

  const isChildActive = childPaths.some((p) => {
    const abs = p === "/" ? "/" : `/${p}`;
    return pathname === abs || pathname.startsWith(`${abs}/`);
  });

  const [open, setOpen] = useState(defaultOpen || isChildActive);

  useEffect(() => {
    if (isChildActive) setOpen(true);
  }, [isChildActive]);

  const toggle = () => setOpen((o) => !o);

  const sharedLabelClass = cn(
    "flex-1 flex items-center gap-3 px-3 py-2 rounded-pill text-sm min-w-0",
    motion.colors,
  );

  return (
    <div>
      <div className="flex items-center gap-0.5">
        {href ? (
          <NavLink
            to={href}
            end={hrefIndex}
            className={({ isActive }) =>
              cn(
                sharedLabelClass,
                isActive
                  ? "bg-plum-voltage/15 text-white"
                  : "text-smoke hover:text-white hover:bg-white/5",
              )
            }
          >
            <span className="relative flex-shrink-0">
              <Icon className="w-4 h-4" />
              {!open && status === "thinking" && (
                <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full border border-plum-voltage/60 border-t-plum-voltage animate-spin lg:hidden" />
              )}
              {!open && status === "attention" && (
                <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-plum-voltage animate-pulse lg:hidden" />
              )}
            </span>
            <span className="hidden lg:block flex-1 truncate">{label}</span>
          </NavLink>
        ) : (
          <button
            type="button"
            onClick={toggle}
            className={cn(
              sharedLabelClass,
              isChildActive
                ? "text-white"
                : "text-smoke hover:text-white hover:bg-white/5",
            )}
          >
            <span className="relative flex-shrink-0">
              <Icon className="w-4 h-4" />
              {!open && status === "thinking" && (
                <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full border border-plum-voltage/60 border-t-plum-voltage animate-spin lg:hidden" />
              )}
              {!open && status === "attention" && (
                <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-plum-voltage animate-pulse lg:hidden" />
              )}
            </span>
            <span className="hidden lg:block flex-1 truncate text-left">{label}</span>
          </button>
        )}

        <button
          type="button"
          onClick={toggle}
          aria-label={open ? "Collapse" : "Expand"}
          className={cn(
            "hidden lg:flex w-7 h-7 items-center justify-center rounded text-white/40 hover:text-white flex-shrink-0",
            motion.colors,
          )}
        >
          <ChevronRight
            className={cn("w-4 h-4", motion.rotate, open && "rotate-90")}
          />
        </button>
      </div>

      <div
        className={cn(
          "hidden lg:grid",
          motion.accordion,
          open ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0",
        )}
      >
        <div className="overflow-hidden">
          <div className="pl-3 pt-0.5 pb-1 space-y-0.5">{children}</div>
        </div>
      </div>
    </div>
  );
}
