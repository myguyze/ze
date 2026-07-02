import type { ReactNode } from "react";

interface ChatLayoutProps {
  children: ReactNode;
  sidebar: ReactNode;
}

export function ChatLayout({ children, sidebar }: ChatLayoutProps) {
  return (
    <div className="flex h-full min-h-0">
      <div className="flex flex-col flex-1 min-w-0 min-h-0 relative">{children}</div>
      {sidebar}
    </div>
  );
}
