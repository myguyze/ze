import { useEffect, useRef, useState } from "react";
import { Plus } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useWebSocket, useWsStore, send } from "@/ws/useWebSocket";
import { useMessages } from "@/messages/useMessages";
import { useSession } from "@/chat/useSession";
import { type InboundFrame } from "@/ws/protocol";
import { MessageBubble } from "./MessageBubble";
import { TypingIndicator } from "./TypingIndicator";
import { ChatInput } from "./ChatInput";
import { SessionSheet } from "./SessionSheet";
import { BackgroundBeamsCanvas } from "@/lib/aceternity/background-beams";
import { GlowingStars } from "@/lib/aceternity/glowing-stars";

type ConnectionState = "connecting" | "connected" | "disconnected";

export function ChatScreen() {
  const threadId = useSession((s) => s.threadId);
  const newSession = useSession((s) => s.newSession);
  const { messages, upsert, edit, loadHistory } = useMessages(threadId);
  const queryClient = useQueryClient();
  const isConnected = useWsStore((s) => s.isConnected);
  const isThinking = useWsStore((s) => s.isThinking);
  const setThinking = useWsStore((s) => s.setThinking);
  const [connState, setConnState] = useState<ConnectionState>("connecting");
  const [showTyping, setShowTyping] = useState(false);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const typingTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    setConnState(isConnected ? "connected" : "connecting");
    if (isConnected) void loadHistory();
  }, [isConnected, threadId, loadHistory]);

  useWebSocket((frame: InboundFrame) => {
    if (frame.type === "message") {
      if (frame.message.thread_id && frame.message.thread_id !== threadId) return;
      upsert(frame.message);
      setThinking(false);
      setShowTyping(false);
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      if (frame.message.role === "assistant" && !frame.message.read) {
        send({ type: "ack", ids: [frame.message.id] });
      }
    }
    if (frame.type === "edit") {
      edit(frame.id, frame.text, frame.components);
    }
    if (frame.type === "typing") {
      setShowTyping(true);
      clearTimeout(typingTimer.current);
      typingTimer.current = setTimeout(() => setShowTyping(false), 3000);
    }
    if (frame.type === "error") {
      setThinking(false);
    }
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, showTyping]);

  useEffect(() => {
    const disconnectTimer = setTimeout(() => {
      if (connState === "connecting") setConnState("disconnected");
    }, 10_000);
    return () => clearTimeout(disconnectTimer);
  }, [connState]);

  function handleSend() {
    const text = input.trim();
    if (!text || isThinking) return;
    setInput("");
    setThinking(true);
    upsert({
      id: crypto.randomUUID(),
      role: "user",
      text,
      components: [],
      read: true,
      created_at: new Date().toISOString(),
      thread_id: threadId,
    });
    send({ type: "message", text, thread_id: threadId });
  }

  function handleNewSession() {
    newSession();
    setInput("");
    setThinking(false);
    setShowTyping(false);
  }

  const isEmpty = messages.length === 0 && connState === "connected";

  return (
    <div className="flex flex-col h-full relative">
      <BackgroundBeamsCanvas className="opacity-40" />

      <div className="relative z-10 flex items-center justify-between px-4 py-3 border-b border-white/10 flex-shrink-0">
        <SessionSheet />
        <button
          type="button"
          onClick={handleNewSession}
          className="flex items-center gap-2 px-3 py-1.5 rounded-[24px] bg-[#8052ff] text-white text-xs font-medium hover:bg-[#8052ff]/90 transition-colors"
        >
          <Plus className="w-3.5 h-3.5" />
          New chat
        </button>
      </div>

      {connState === "connecting" && (
        <div className="relative z-10 mx-4 mt-3 flex items-center gap-2 px-4 py-2 rounded-[24px] border border-[#ffb829]/40 text-[#ffb829] text-xs">
          <span className="w-1.5 h-1.5 rounded-full bg-[#ffb829] animate-pulse" />
          Connecting to Ze…
        </div>
      )}
      {connState === "disconnected" && (
        <div className="relative z-10 mx-4 mt-3 flex items-center justify-between px-4 py-2 rounded-[24px] border border-white/15 text-white text-xs">
          <span className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
            Could not connect.
          </span>
          <button
            onClick={() => { setConnState("connecting"); }}
            className="text-[#8052ff] underline"
          >
            Retry
          </button>
        </div>
      )}

      {isEmpty && (
        <div className="relative z-10 flex-1 flex flex-col items-center justify-center gap-6">
          <GlowingStars className="rounded-[24px]" count={80} />
          <p className="text-[48px] font-extralight tracking-tight text-white leading-none select-none">
            Ze
          </p>
          <p className="text-sm text-[#9a9a9a]">Your personal AI assistant</p>
          <button
            onClick={() => send({ type: "command", name: "capabilities" })}
            className="px-4 py-2 rounded-[24px] border border-[#8052ff]/50 text-[#8052ff] text-xs hover:border-[#8052ff] transition-colors"
          >
            What can you help me with?
          </button>
        </div>
      )}

      {!isEmpty && (
        <div className="relative z-10 flex-1 overflow-y-auto px-4 py-4 space-y-4 min-h-0">
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
          {showTyping && <TypingIndicator />}
          <div ref={bottomRef} />
        </div>
      )}

      <div className="relative z-10 flex-shrink-0">
        <ChatInput value={input} onChange={setInput} onSend={handleSend} />
      </div>
    </div>
  );
}
