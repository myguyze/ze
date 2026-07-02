import { useQuery } from "@tanstack/react-query";
import { listSessions } from "@myguyze/ze-client";
import type { SessionSchema } from "@myguyze/ze-client";
import { SessionRow, useSession } from "@/entities/session";
import { queryKeys } from "@/shared/lib";

export function SessionList() {
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
    <div className="space-y-2 px-3 py-3">
      {isLoading &&
        [1, 2, 3].map((i) => (
          <div key={i} className="h-[4.5rem] animate-pulse rounded-pill border border-white/10 bg-white/[0.02]" />
        ))}

      {sessions?.length === 0 && (
        <p className="px-3 py-8 text-center text-sm text-smoke">No past sessions yet.</p>
      )}

      {sessions?.map((session) => (
        <SessionRow
          key={session.id}
          session={session}
          active={session.id === threadId}
          onSelect={() => selectSession(session.id)}
        />
      ))}
    </div>
  );
}
