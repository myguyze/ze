import type { ReactNode } from "react";
import { cn } from "@/shared/lib/cn";

interface DashboardGridProps {
  children: ReactNode;
  className?: string;
}

export function DashboardGrid({ children, className }: DashboardGridProps) {
  return (
    <div className={cn("grid grid-cols-1 xl:grid-cols-[5fr_7fr] gap-8", className)}>
      {children}
    </div>
  );
}

interface DashboardGridColumnProps {
  children: ReactNode;
  className?: string;
  scrollable?: boolean;
}

export function DashboardGridMain({ children, className }: DashboardGridColumnProps) {
  return <div className={cn("flex flex-col gap-6", className)}>{children}</div>;
}

export function DashboardGridAside({ children, className, scrollable }: DashboardGridColumnProps) {
  return (
    <div
      className={cn(
        "flex flex-col gap-6",
        scrollable && "overflow-y-auto min-h-0",
        className,
      )}
    >
      {children}
    </div>
  );
}
