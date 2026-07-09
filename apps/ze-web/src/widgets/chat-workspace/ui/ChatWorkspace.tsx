import { useEffect, useMemo, useState } from "react";
import { ChatMessageList, ChatInput, ConfirmBar } from "@/entities/message";
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

  const isEmpty = messages.length === 0 && connState === "connected";

  return (
    <ChatLayout sidebar={<ChatSidePanel threadId={threadId} assistantMessageIds={assistantMessageIds} />}>
      <BackgroundBeamsCanvas className="opacity-40" />

      {connState === "connecting" && (
        <div className="relative z-10 mb-3 flex w-full items-center gap-2 rounded-pill border border-amber-spark/40 px-4 py-2 text-xs text-amber-spark">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-spark animate-pulse" />
          Connecting to Ze…
        </div>
      )}
      {connState === "disconnected" && (
        <div className="relative z-10 mb-3 flex w-full items-center justify-between rounded-pill border border-white/15 px-4 py-2 text-xs text-white">
          <span className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-destructive" />
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
