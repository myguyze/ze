import { useCallback, useRef, useState } from "react";
import { type Message } from "@/ws/protocol";
import { api } from "@/lib/api";
import { send } from "@/ws/useWebSocket";

const HISTORY_DAYS = 7;

export function useMessages() {
  const [messages, setMessages] = useState<Map<string, Message>>(new Map());
  const loadedRef = useRef(false);

  const upsert = useCallback((msg: Message) => {
    setMessages((prev) => {
      const next = new Map(prev);
      next.set(msg.id, msg);
      return next;
    });
  }, []);

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
    if (loadedRef.current) return;
    loadedRef.current = true;

    const since = new Date(Date.now() - HISTORY_DAYS * 86_400_000).toISOString();
    try {
      const history = await api.get<Message[]>(`/api/messages?since=${since}&limit=200`);
      setMessages((prev) => {
        const next = new Map(prev);
        for (const msg of history) next.set(msg.id, msg);
        return next;
      });

      const unread = history
        .filter((m) => m.role === "assistant" && !m.read)
        .map((m) => m.id);
      if (unread.length > 0) send({ type: "ack", ids: unread });
    } catch {
      // non-fatal — WS unread push covers the gap
    }
  }, []);

  const sorted = [...messages.values()].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  );

  return { messages: sorted, upsert, edit, loadHistory };
}
