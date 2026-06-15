import { useCallback, useEffect, useRef, useState } from "react";
import { type Message } from "@/features/websocket/protocol";
import { api } from "@/lib/api";
import { send } from "@/features/websocket/useWebSocket";

export function useMessages(threadId: string) {
  const [messages, setMessages] = useState<Map<string, Message>>(new Map());
  const loadedThreadRef = useRef<string | null>(null);

  useEffect(() => {
    if (loadedThreadRef.current !== threadId) {
      setMessages(new Map());
      loadedThreadRef.current = null;
    }
  }, [threadId]);

  const upsert = useCallback(
    (msg: Message) => {
      if (msg.thread_id && msg.thread_id !== threadId) return;
      setMessages((prev) => {
        const next = new Map(prev);
        next.set(msg.id, msg);
        return next;
      });
    },
    [threadId],
  );

  const edit = useCallback((id: string, text?: string, components?: Message["components"]) => {
    setMessages((prev) => {
      const existing = prev.get(id);
      if (!existing) return prev;
      const next = new Map(prev);
      next.set(id, {
        ...existing,
        ...(text !== undefined && { text }),
        ...(components !== undefined && { components }),
      });
      return next;
    });
  }, []);

  const loadHistory = useCallback(async () => {
    if (loadedThreadRef.current === threadId) return;
    loadedThreadRef.current = threadId;

    try {
      const history = await api.get<Message[]>(
        `/api/messages?thread_id=${encodeURIComponent(threadId)}&limit=200`,
      );
      setMessages(new Map(history.map((msg) => [msg.id, msg])));

      const unread = history
        .filter((m) => m.role === "assistant" && !m.read)
        .map((m) => m.id);
      if (unread.length > 0) send({ type: "ack", ids: unread });
    } catch {
      loadedThreadRef.current = null;
    }
  }, [threadId]);

  const reload = useCallback(async () => {
    loadedThreadRef.current = null;
    await loadHistory();
  }, [loadHistory]);

  const sorted = [...messages.values()].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  );

  return { messages: sorted, upsert, edit, loadHistory, reload };
}
