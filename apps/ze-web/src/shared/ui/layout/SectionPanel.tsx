import type { ReactNode } from "react";
import { cn } from "@/shared/lib/cn";

interface SectionPanelProps {
  children: ReactNode;
  className?: string;
}

export function SectionPanel({ children, className }: SectionPanelProps) {
  return (
    <div className={cn("rounded-2xl bg-white/[0.025] border border-white/[0.07] p-5", className)}>
      {children}
    </div>
  );
}
