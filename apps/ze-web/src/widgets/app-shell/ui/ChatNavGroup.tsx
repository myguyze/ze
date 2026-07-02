import { useQuery } from "@tanstack/react-query";
import { listSessions } from "@myguyze/ze-client";
import type { SessionSchema } from "@myguyze/ze-client";
import { MessageCircle, Plus } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useSession } from "@/entities/session";
import { cn } from "@/shared/lib/cn";
import { motion } from "@/shared/lib/motion";
import { queryKeys } from "@/shared/lib";
import { NavGroup } from "./NavGroup";

const MAX_SESSIONS = 8;

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

function SessionItem({ session, active, onSelect }: {
  session: SessionSchema;
  active: boolean;
  onSelect: () => void;
}) {
  const label = session.title ?? session.preview ?? "Untitled chat";
  return (
    <button
      type="button"
      onClick={onSelect}
      title={`${label} · ${formatRelative(session.last_active_at)}`}
      className={cn(
        "w-full text-left px-3 py-1.5 rounded-pill text-xs truncate",
        motion.colors,
        active
          ? "bg-plum-voltage/15 text-white"
          : "text-smoke hover:text-white hover:bg-white/5",
      )}
    >
      {label}
    </button>
  );
}

export function ChatNavGroup() {
  const threadId = useSession((s) => s.threadId);
  const selectSession = useSession((s) => s.selectSession);
  const newSession = useSession((s) => s.newSession);
  const navigate = useNavigate();

  const { data: sessions, isLoading } = useQuery<SessionSchema[]>({
    queryKey: queryKeys.sessions,
    queryFn: async () => {
      const { data } = await listSessions();
      return data ?? [];
    },
  });

  const recent = sessions?.slice(0, MAX_SESSIONS) ?? [];

  function handleNewSession() {
    newSession();
    navigate("/");
  }

  function handleSelectSession(id: string) {
    selectSession(id);
    navigate("/");
  }

  return (
    <NavGroup icon={MessageCircle} label="Chat" href="/" hrefIndex defaultOpen childPaths={["/"]}>
      <button
        type="button"
        onClick={handleNewSession}
        className={cn(
          "w-full flex items-center gap-2 px-3 py-1.5 rounded-pill text-xs",
          motion.colors,
          "text-smoke hover:text-white hover:bg-white/5",
        )}
      >
        <Plus className="w-3 h-3 flex-shrink-0" />
        New chat
      </button>

      {isLoading &&
        [1, 2, 3].map((i) => (
          <div key={i} className="h-7 mx-0.5 rounded-pill bg-white/5 animate-pulse" />
        ))}

      {recent.map((session) => (
        <SessionItem
          key={session.id}
          session={session}
          active={session.id === threadId}
          onSelect={() => handleSelectSession(session.id)}
        />
      ))}

      {!isLoading && recent.length === 0 && (
        <p className="px-3 py-1.5 text-xs text-smoke/50">No past chats yet.</p>
      )}
    </NavGroup>
  );
}
