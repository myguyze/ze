import { Plus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { ChatMessageList, ChatInput, ConfirmBar } from "@/entities/message";
import { useSession } from "@/entities/session";
import { reconnect, send } from "@/shared/api";
import { useTopBarQuickActions } from "@/shared/lib";
import { BackgroundBeamsCanvas } from "@/shared/effects/background-beams";
import { GlowingStars } from "@/shared/effects/glowing-stars";
import { useChatWorkspace } from "../model/useChatWorkspace";
import { ChatLayout } from "./ChatLayout";
import { ChatSidePanel } from "./ChatSidePanel";
import { ChatSidePanelQuickActions } from "./ChatSidePanelQuickActions";

type ConnectionState = "connecting" | "connected" | "disconnected";

export function ChatWorkspace() {
  const newSession = useSession((s) => s.newSession);
  const {
    threadId,
    messages,
    showTyping,
    typingText,
    streamingText,
    isThinking,
    isConnected,
    pendingConfirm,
    sendMessage,
    respondToConfirm,
    resetInteraction,
  } = useChatWorkspace();

  const [input, setInput] = useState("");
  const [connTimedOut, setConnTimedOut] = useState(false);
  const connState: ConnectionState =
    isConnected ? "connected" : connTimedOut ? "disconnected" : "connecting";

  const quickActions = useMemo(() => <ChatSidePanelQuickActions />, []);
  useTopBarQuickActions(quickActions);

  const assistantMessageIds = useMemo(
    () =>
      messages
        .filter((m) => m.role === "assistant" && m.id && m.id !== "__streaming__")
        .map((m) => String(m.id)),
    [messages],
  );

  useEffect(() => {
    if (isConnected) return;
    const disconnectTimer = setTimeout(() => setConnTimedOut(true), 10_000);
    return () => clearTimeout(disconnectTimer);
  }, [isConnected]);

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
    <ChatLayout sidebar={<ChatSidePanel threadId={threadId} assistantMessageIds={assistantMessageIds} />}>
      <BackgroundBeamsCanvas className="opacity-40" />

      <div className="relative z-10 flex items-center justify-end px-4 py-3 border-b border-white/10 flex-shrink-0">
        <button
          type="button"
          onClick={handleNewSession}
          className="flex items-center gap-2 px-3 py-1.5 rounded-pill bg-plum-voltage text-white text-xs font-medium hover:bg-plum-voltage/90 transition-colors"
        >
          <Plus className="w-3.5 h-3.5" />
          New chat
        </button>
      </div>

      {connState === "connecting" && (
        <div className="relative z-10 mx-4 mt-3 flex items-center gap-2 px-4 py-2 rounded-pill border border-amber-spark/40 text-amber-spark text-xs">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-spark animate-pulse" />
          Connecting to Ze…
        </div>
      )}
      {connState === "disconnected" && (
        <div className="relative z-10 mx-4 mt-3 flex items-center justify-between px-4 py-2 rounded-pill border border-white/15 text-white text-xs">
          <span className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
            Could not connect.
          </span>
          <button
            onClick={() => {
              setConnTimedOut(false);
              reconnect();
            }}
            className="text-plum-voltage underline"
          >
            Retry
          </button>
        </div>
      )}

      {isEmpty && (
        <div className="relative z-10 flex-1 flex flex-col items-center justify-center gap-6">
          <GlowingStars className="rounded-pill" count={80} />
          <p className="text-[48px] font-extralight tracking-tight text-white leading-none select-none">
            Ze
          </p>
          <p className="text-sm text-smoke">Your personal AI assistant</p>
          <button
            onClick={() => send({ type: "command", name: "capabilities" })}
            className="px-4 py-2 rounded-pill border border-plum-voltage/50 text-plum-voltage text-xs hover:border-plum-voltage transition-colors"
          >
            What can you help me with?
          </button>
        </div>
      )}

      {!isEmpty && (
        <div className="relative z-10 flex-1 min-h-0 flex flex-col">
          <ChatMessageList
            messages={messages}
            showTyping={showTyping}
            typingText={typingText}
            streamingText={streamingText}
          />
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
    </ChatLayout>
  );
}
