import type { ReactNode } from "react";
import { cn } from "@/shared/lib/cn";
import { DashboardSectionTitle } from "../DashboardSectionTitle";
import { SectionPanel } from "../SectionPanel";

interface BreakdownPanelProps {
  title: ReactNode;
  children?: ReactNode;
  isEmpty?: boolean;
  emptyMessage?: string;
  className?: string;
  scrollable?: boolean;
}

export function BreakdownPanel({
  title,
  children,
  isEmpty,
  emptyMessage = "Nothing to show yet.",
  className,
  scrollable = true,
}: BreakdownPanelProps) {
  return (
    <SectionPanel
      className={cn(
        "flex flex-col",
        scrollable && "min-h-[280px] xl:min-h-0 xl:h-full xl:overflow-hidden",
        className,
      )}
    >
      <DashboardSectionTitle>{title}</DashboardSectionTitle>

      {isEmpty ? (
        <p className="text-sm text-smoke">{emptyMessage}</p>
      ) : scrollable ? (
        <div className="flex-1 min-h-0 overflow-y-auto -mx-1 px-1">{children}</div>
      ) : (
        children
      )}
    </SectionPanel>
  );
}
