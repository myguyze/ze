import type { MessageSchema as Message } from "@myguyze/ze-client";
import { useEffect, useRef, useState } from "react";
import { ChatErrorBoundary } from "@/shared/ui";
import { useSession } from "@/entities/session";
import { MessageBubble } from "./MessageBubble";
import { TypingIndicator } from "./TypingIndicator";

interface ChatMessageListProps {
  messages: Message[];
  showTyping: boolean;
  typingText?: string | null;
  streamingText?: string | null;
  className?: string;
}

export function ChatMessageList({
  messages,
  showTyping,
  typingText,
  streamingText,
  className,
}: ChatMessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const highlightMessageId = useSession((s) => s.highlightMessageId);
  const setHighlightMessage = useSession((s) => s.setHighlightMessage);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, showTyping, streamingText]);

  useEffect(() => {
    if (!highlightMessageId) return;
    const el = document.getElementById(`message-${highlightMessageId}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      setUnavailable(false);
    } else if (messages.length > 0) {
      setUnavailable(true);
    }
  }, [highlightMessageId, messages]);

  const streamingMessage: Message | null = streamingText?.trim()
    ? {
        id: "__streaming__",
        role: "assistant",
        text: streamingText,
        components: [],
        read: true,
        created_at: new Date().toISOString(),
        thread_id: null,
      }
    : null;

  return (
    <div
      className={className ?? "min-h-0 flex-1 space-y-4 overflow-y-auto py-2"}
      onClick={() => {
        if (highlightMessageId) setHighlightMessage(null);
      }}
    >
      {highlightMessageId && unavailable && (
        <p className="text-center text-xs text-smoke">
          The originating message is no longer available in this conversation.
        </p>
      )}
      {messages.map((msg) => (
        <ChatErrorBoundary key={msg.id}>
          <div id={`message-${msg.id}`}>
            <MessageBubble message={msg} highlighted={msg.id === highlightMessageId} />
          </div>
        </ChatErrorBoundary>
      ))}
      {streamingMessage && (
        <ChatErrorBoundary key="__streaming__">
          <MessageBubble message={streamingMessage} />
        </ChatErrorBoundary>
      )}
      {showTyping && !streamingText && <TypingIndicator text={typingText} />}
      <div ref={bottomRef} />
    </div>
  );
}
