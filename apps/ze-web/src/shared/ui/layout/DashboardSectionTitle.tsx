import type { ReactNode } from "react";
import { cn } from "@/shared/lib/cn";

interface DashboardSectionTitleProps {
  children: ReactNode;
  className?: string;
  tone?: "default" | "warning";
}

export function DashboardSectionTitle({
  children,
  className,
  tone = "default",
}: DashboardSectionTitleProps) {
  return (
    <p
      className={cn(
        "text-xs font-semibold uppercase tracking-widest mb-5",
        tone === "warning" ? "text-amber-spark/80" : "text-white/40",
        className,
      )}
    >
      {children}
    </p>
  );
}
