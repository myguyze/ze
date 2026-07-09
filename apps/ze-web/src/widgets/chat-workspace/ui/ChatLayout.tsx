import type { ReactNode } from "react";
import { ChatShell } from "@/shared/ui";

interface ChatLayoutProps {
  children: ReactNode;
  sidebar: ReactNode;
}

export function ChatLayout({ children, sidebar }: ChatLayoutProps) {
  return (
    <div className="flex h-full min-h-0">
      <div className="relative flex min-h-0 min-w-0 flex-1 flex-col">
        <ChatShell>{children}</ChatShell>
      </div>
      {sidebar}
    </div>
  );
}
