import { useQuery } from "@tanstack/react-query";
import { History } from "lucide-react";
import { listSessions } from "@ze/client";
import type { SessionSchema } from "@ze/client";
import { queryKeys } from "@/lib/queryKeys";
import { useSession } from "@/features/chat/hooks/useSession";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { cn } from "@/lib/cn";

function formatRelative(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

export function SessionSheet() {
  const threadId = useSession((s) => s.threadId);
  const selectSession = useSession((s) => s.selectSession);

  const { data: sessions, isLoading } = useQuery<SessionSchema[]>({
    queryKey: queryKeys.sessions,
    queryFn: async () => {
      const { data } = await listSessions();
      return data ?? [];
    },
  });

  return (
    <Sheet>
      <SheetTrigger asChild>
        <button
          type="button"
          className="flex items-center gap-2 px-3 py-1.5 rounded-pill border border-white/10 text-xs text-smoke hover:text-white hover:border-white/20 transition-colors"
          aria-label="Session history"
        >
          <History className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">History</span>
        </button>
      </SheetTrigger>

      <SheetContent side="right" className="flex flex-col p-0">
        <div className="px-4 py-5 border-b border-white/10 pr-12">
          <p className="text-xs font-semibold tracking-widest uppercase text-smoke mb-1">Sessions</p>
          <p className="text-lg font-extralight text-white">Past conversations</p>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-3 space-y-1">
          {isLoading &&
            [1, 2, 3].map((i) => (
              <div key={i} className="h-14 rounded-pill border border-white/10 animate-pulse" />
            ))}

          {sessions?.length === 0 && (
            <p className="px-3 py-8 text-center text-sm text-smoke">No past sessions yet.</p>
          )}

          {sessions?.map((session) => {
            const active = session.id === threadId;
            const label = session.title ?? session.preview ?? "Untitled chat";
            return (
              <button
                key={session.id}
                type="button"
                onClick={() => selectSession(session.id)}
                className={cn(
                  "w-full text-left px-4 py-3 rounded-pill transition-colors",
                  active
                    ? "bg-plum-voltage/15 border border-plum-voltage/30"
                    : "border border-transparent hover:border-white/10 hover:bg-white/5",
                )}
              >
                <p className="text-sm text-white truncate">{label}</p>
                {session.preview && session.title && (
                  <p className="text-xs text-smoke truncate mt-0.5">{session.preview}</p>
                )}
                <p className="text-[10px] text-smoke mt-1">{formatRelative(session.last_active_at)}</p>
              </button>
            );
          })}
        </div>
      </SheetContent>
    </Sheet>
  );
}
