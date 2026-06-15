import { useEffect, useRef } from "react";
import { type Message } from "@/features/websocket/protocol";
import { MessageBubble } from "./MessageBubble";
import { TypingIndicator } from "./TypingIndicator";

interface ChatMessageListProps {
  messages: Message[];
  showTyping: boolean;
  className?: string;
}

export function ChatMessageList({ messages, showTyping, className }: ChatMessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, showTyping]);

  return (
    <div className={className ?? "flex-1 overflow-y-auto px-4 py-4 space-y-4 min-h-0"}>
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
      {showTyping && <TypingIndicator />}
      <div ref={bottomRef} />
    </div>
  );
}
