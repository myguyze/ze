import type { ReactNode } from "react";
import { cn } from "@/shared/lib/cn";

interface ChatShellProps {
  children: ReactNode;
  className?: string;
}

/** Full-height chat column with the same horizontal rhythm as PageShell / ListPage. */
export function ChatShell({ children, className }: ChatShellProps) {
  return (
    <div className={cn("flex h-full min-h-0 w-full flex-col px-6 md:px-10 pb-10 pt-4", className)}>
      {children}
    </div>
  );
}
