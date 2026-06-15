import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { reconnect, send } from "@/features/websocket/useWebSocket";
import { useChatSession } from "@/features/chat/hooks/useChatSession";
import { useSession } from "@/features/chat/hooks/useSession";
import { ChatMessageList } from "@/features/chat/components/ChatMessageList";
import { ChatInput } from "@/features/chat/components/ChatInput";
import { ConfirmBar } from "@/features/chat/components/ConfirmBar";
import { SessionSheet } from "@/features/chat/components/SessionSheet";
import { BackgroundBeamsCanvas } from "@/lib/aceternity/background-beams";
import { GlowingStars } from "@/lib/aceternity/glowing-stars";

type ConnectionState = "connecting" | "connected" | "disconnected";

export function ChatPage() {
  const newSession = useSession((s) => s.newSession);
  const {
    messages,
    showTyping,
    isThinking,
    isConnected,
    pendingConfirm,
    sendMessage,
    respondToConfirm,
    resetInteraction,
  } = useChatSession();

  const [connState, setConnState] = useState<ConnectionState>("connecting");
  const [input, setInput] = useState("");

  useEffect(() => {
    setConnState(isConnected ? "connected" : "connecting");
  }, [isConnected]);

  useEffect(() => {
    const disconnectTimer = setTimeout(() => {
      if (connState === "connecting") setConnState("disconnected");
    }, 10_000);
    return () => clearTimeout(disconnectTimer);
  }, [connState]);

  function handleSend() {
    if (sendMessage(input)) {
      setInput("");
    }
  }

  function handleNewSession() {
    newSession();
    setInput("");
    resetInteraction();
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
            onClick={() => { setConnState("connecting"); reconnect(); }}
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
        <div className="relative z-10 flex-1 min-h-0 flex flex-col">
          <ChatMessageList messages={messages} showTyping={showTyping} />
        </div>
      )}

      {pendingConfirm && (
        <ConfirmBar
          prompt={pendingConfirm.prompt}
          actions={pendingConfirm.actions}
          onConfirm={respondToConfirm}
        />
      )}

      <div className="relative z-10 flex-shrink-0">
        <ChatInput
          value={input}
          onChange={setInput}
          onSend={handleSend}
          disabled={isThinking}
        />
      </div>
    </div>
  );
}
