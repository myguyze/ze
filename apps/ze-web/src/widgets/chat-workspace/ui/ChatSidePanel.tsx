import { TraceContent } from "@/widgets/trace-panel";
import { useSessionsQuery } from "@/entities/session";
import { useChatSidePanelStore } from "@/features/chat-side-panel";
import { useTraceStore } from "@/features/trace-state";
import { SidePanel } from "@/shared/ui";
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
      <p className="text-[10px] text-smoke/60 mt-0.5">{detail}</p>
    </div>
  );
}

function HistoryPanelHeader() {
  const { data: browsePages, isLoading } = useSessionsQuery(1);
  const firstPage = browsePages?.pages[0];
  const hasMore = Boolean(firstPage?.next_before);

  let detail = "Past conversations";
  if (!isLoading && firstPage) {
    if (firstPage.items.length === 0) {
      detail = "No past sessions yet";
    } else if (hasMore) {
      detail = "Scroll for older conversations";
    }
  }

  return (
    <div className="px-3 py-2.5 flex-shrink-0">
      <p className="text-xs font-medium text-white">History</p>
      <p className="text-[10px] text-smoke/60 mt-0.5">{detail}</p>
    </div>
  );
}

function ChatSidePanelHeader() {
  const tab = useChatSidePanelStore((s) => s.tab);
  return (
    <div className="border-b border-white/[0.06]">
      {tab === "trace" ? <TracePanelHeader /> : <HistoryPanelHeader />}
    </div>
  );
}

export function ChatSidePanel({ threadId, assistantMessageIds }: ChatSidePanelProps) {
  const open = useChatSidePanelStore((s) => s.open);
  const width = useChatSidePanelStore((s) => s.width);
  const tab = useChatSidePanelStore((s) => s.tab);
  const setOpen = useChatSidePanelStore((s) => s.setOpen);
  const setWidth = useChatSidePanelStore((s) => s.setWidth);

  return (
    <SidePanel
      open={open}
      width={width}
      onWidthChange={setWidth}
      onClose={() => setOpen(false)}
      header={<ChatSidePanelHeader />}
    >
      {tab === "trace" ? (
        <TraceContent threadId={threadId} assistantMessageIds={assistantMessageIds} />
      ) : (
        <SessionList />
      )}
    </SidePanel>
  );
}
