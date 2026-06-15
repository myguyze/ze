import { useRef, useState } from "react";
import { useMessages } from "@/messages/useMessages";
import { useFrame, send } from "@/ws/useWebSocket";

export function useChat(threadId: string) {
  const { messages, upsert, edit, loadHistory, reload } = useMessages(threadId);
  const [showTyping, setShowTyping] = useState(false);
  const typingTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useFrame("message", (frame) => {
    if (frame.message.thread_id && frame.message.thread_id !== threadId) return;
    upsert(frame.message);
    setShowTyping(false);
    clearTimeout(typingTimer.current);
    if (frame.message.role === "assistant" && !frame.message.read) {
      send({ type: "ack", ids: [frame.message.id] });
    }
    // Reload from server to reconcile optimistic user message (temp UUID → real ID).
    if (frame.message.role === "assistant") {
      void reload();
    }
  });

  useFrame("edit", (frame) => {
    edit(frame.id, frame.text, frame.components);
  });

  useFrame("typing", () => {
    setShowTyping(true);
    clearTimeout(typingTimer.current);
    typingTimer.current = setTimeout(() => setShowTyping(false), 3_000);
  });

  // Clear typing on events that signal the assistant is done
  useFrame("confirm_request", () => {
    setShowTyping(false);
    clearTimeout(typingTimer.current);
  });

  useFrame("error", () => {
    setShowTyping(false);
    clearTimeout(typingTimer.current);
  });

  return { messages, loadHistory, upsert, showTyping };
}
