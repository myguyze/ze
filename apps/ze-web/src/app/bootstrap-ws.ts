import { useSession } from "@/entities/session";
import { registerThreadIdGetter, reconnect } from "@/shared/api";

export function bootstrapWs() {
  registerThreadIdGetter(() => useSession.getState().threadId);

  let activeThreadId = useSession.getState().threadId;
  useSession.subscribe((state) => {
    if (state.threadId === activeThreadId) return;
    activeThreadId = state.threadId;
    reconnect();
  });
}
