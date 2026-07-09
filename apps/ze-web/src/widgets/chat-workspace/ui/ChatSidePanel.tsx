import { useState } from "react";
import { TraceContent } from "@/widgets/trace-panel";
import { useChatSidePanelStore } from "@/features/chat-side-panel";
import { useTraceStore } from "@/features/trace-state";
import { useSessionsQuery } from "@/entities/session";
import { cn, motion } from "@/shared/lib";
import { SearchBar, SidePanel } from "@/shared/ui";
import { SessionList } from "./SessionList";

interface ChatSidePanelProps {
  threadId: string;
  assistantMessageIds: string[];
}

function TracePanelHeader() {
  const traces = useTraceStore((s) => s.traces);
  const pending = useTraceStore((s) => s.pending);

  let detail = "Routing, memory, and tools per message";
  if (pending) {
    detail = "Live trace in progress…";
  } else if (traces.length > 0) {
    detail = `${traces.length} turn${traces.length !== 1 ? "s" : ""} in this chat`;
  }

  return (
    <div className="px-3 py-2.5 flex-shrink-0">
      <p className="text-xs font-medium text-white">Trace</p>
      <p className="text-[10px] text-smoke/80 mt-0.5">{detail}</p>
    </div>
  );
}

interface HistoryPanelHeaderProps {
  searchQuery: string;
  onSearchChange: (value: string) => void;
}

function HistoryPanelHeader({ searchQuery, onSearchChange }: HistoryPanelHeaderProps) {
  const { data: browsePages, isLoading } = useSessionsQuery(1);
  const firstPage = browsePages?.pages[0];
  const hasMore = Boolean(firstPage?.next_before);
  const trimmed = searchQuery.trim();

  let detail = "Past conversations";
  if (trimmed.length >= 2) {
    detail = `Searching for “${trimmed}”`;
  } else if (!isLoading && firstPage) {
    if (firstPage.items.length === 0) {
      detail = "No past sessions yet";
    } else if (hasMore) {
      detail = "Scroll for older conversations";
    }
  }

  return (
    <div className="flex-shrink-0 px-3 pt-2.5 pb-3">
      <p className="text-xs font-medium text-white">History</p>
      <p className="mt-0.5 text-[10px] text-smoke/80">{detail}</p>
      <SearchBar
        value={searchQuery}
        onChange={onSearchChange}
        placeholder="Search conversations…"
        className="mt-2.5 w-full"
      />
    </div>
  );
}

function ChatSidePanelHeader({
  searchQuery,
  onSearchChange,
}: {
  searchQuery: string;
  onSearchChange: (value: string) => void;
}) {
  const tab = useChatSidePanelStore((s) => s.tab);
  const isTrace = tab === "trace";

  return (
    <div className="relative border-b border-white/[0.06]">
      <div
        className={cn(
          motion.fade,
          isTrace ? "relative opacity-100" : "pointer-events-none absolute inset-x-0 top-0 opacity-0",
        )}
      >
        <TracePanelHeader />
      </div>
      <div
        className={cn(
          motion.fade,
          isTrace ? "pointer-events-none absolute inset-x-0 top-0 opacity-0" : "relative opacity-100",
        )}
      >
        <HistoryPanelHeader searchQuery={searchQuery} onSearchChange={onSearchChange} />
      </div>
    </div>
  );
}

export function ChatSidePanel({ threadId, assistantMessageIds }: ChatSidePanelProps) {
  const open = useChatSidePanelStore((s) => s.open);
  const width = useChatSidePanelStore((s) => s.width);
  const tab = useChatSidePanelStore((s) => s.tab);
  const setOpen = useChatSidePanelStore((s) => s.setOpen);
  const setWidth = useChatSidePanelStore((s) => s.setWidth);
  const [searchQuery, setSearchQuery] = useState("");

  return (
    <SidePanel
      open={open}
      width={width}
      onWidthChange={setWidth}
      onClose={() => setOpen(false)}
      header={<ChatSidePanelHeader searchQuery={searchQuery} onSearchChange={setSearchQuery} />}
    >
      <div
        className={cn(
          "absolute inset-0 overflow-y-auto",
          motion.fade,
          tab === "trace" ? "z-10 opacity-100" : "pointer-events-none z-0 opacity-0",
        )}
      >
        <TraceContent threadId={threadId} assistantMessageIds={assistantMessageIds} />
      </div>
      <div
        className={cn(
          "absolute inset-0 overflow-y-auto",
          motion.fade,
          tab === "history" ? "z-10 opacity-100" : "pointer-events-none z-0 opacity-0",
        )}
      >
        <SessionList searchQuery={searchQuery} />
      </div>
    </SidePanel>
  );
}
