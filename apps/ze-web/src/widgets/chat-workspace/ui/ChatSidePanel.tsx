import { listSessions } from "@myguyze/ze-client";
import { useQuery } from "@tanstack/react-query";
import { TraceContent } from "@/widgets/trace-panel";
import { useChatSidePanelStore } from "@/features/chat-side-panel";
import { useTraceStore } from "@/features/trace-state";
import { queryKeys } from "@/shared/lib";
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
  const { data: sessions, isLoading } = useQuery({
    queryKey: queryKeys.sessions,
    queryFn: async () => {
      const { data } = await listSessions();
      return data ?? [];
    },
  });

  let detail = "Past conversations";
  if (!isLoading && sessions) {
    detail =
      sessions.length === 0
        ? "No past sessions yet"
        : `${sessions.length} conversation${sessions.length !== 1 ? "s" : ""}`;
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
