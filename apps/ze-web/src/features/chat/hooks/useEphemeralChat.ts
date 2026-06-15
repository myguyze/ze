import { useEffect, useRef, useState } from "react";
import { useFrame } from "@/features/websocket/useWebSocket";
import { type Message } from "@/features/websocket/protocol";

interface UseEphemeralChatOptions {
  active: boolean;
  threadId: string;
  onMessage?: () => void;
}

export function useEphemeralChat({ active, threadId, onMessage }: UseEphemeralChatOptions) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [showTyping, setShowTyping] = useState(false);
  const typingTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const prevActiveRef = useRef(active);

  useEffect(() => {
    if (active && !prevActiveRef.current) {
      setMessages([]);
      setShowTyping(false);
    }
    prevActiveRef.current = active;
  }, [active]);

  useFrame("message", (frame) => {
    if (!active) return;
    if (frame.message.thread_id && frame.message.thread_id !== threadId) return;
    setMessages((prev) => [...prev, frame.message]);
    setShowTyping(false);
    clearTimeout(typingTimer.current);
    onMessage?.();
  });

  useFrame("typing", () => {
    if (!active) return;
    setShowTyping(true);
    clearTimeout(typingTimer.current);
    typingTimer.current = setTimeout(() => setShowTyping(false), 3_000);
  });

  return { messages, showTyping };
}
