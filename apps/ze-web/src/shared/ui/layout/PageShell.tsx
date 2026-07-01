import type { ReactNode } from "react";
import { cn } from "@/shared/lib/cn";

interface PageShellProps {
  children: ReactNode;
  className?: string;
}

export function PageShell({ children, className }: PageShellProps) {
  return (
    <div className={cn("px-6 md:px-10 py-8 space-y-8", className)}>
      {children}
    </div>
  );
}
