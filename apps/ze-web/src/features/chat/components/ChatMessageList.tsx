import { useEffect, useRef } from "react";
import type { MessageSchema as Message } from "@ze/client";
import { MessageBubble } from "./MessageBubble";
import { TypingIndicator } from "./TypingIndicator";
import { ChatErrorBoundary } from "@/components/layout/ChatErrorBoundary";

interface ChatMessageListProps {
  messages: Message[];
  showTyping: boolean;
  typingText?: string | null;
  streamingText?: string | null;
  className?: string;
}

export function ChatMessageList({ messages, showTyping, typingText, streamingText, className }: ChatMessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, showTyping, streamingText]);

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
    <div className={className ?? "flex-1 overflow-y-auto px-4 py-4 space-y-4 min-h-0"}>
      {messages.map((msg) => (
        <ChatErrorBoundary key={msg.id}>
          <MessageBubble message={msg} />
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
