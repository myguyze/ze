import { useRef, useState } from "react";
import { useFrame } from "@/features/websocket/useWebSocket";

export function useTypingState(active: boolean) {
  const [showTyping, setShowTyping] = useState(false);
  const [typingText, setTypingText] = useState<string | null>(null);
  const typingTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  function clearTyping() {
    setShowTyping(false);
    setTypingText(null);
    clearTimeout(typingTimer.current);
  }

  useFrame("typing", (frame) => {
    if (!active) return;
    setShowTyping(true);
    setTypingText(frame.text ?? null);
    clearTimeout(typingTimer.current);
    typingTimer.current = setTimeout(() => {
      setShowTyping(false);
      setTypingText(null);
    }, 3_000);
  });

  return { showTyping, typingText, clearTyping };
}
