import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useMessages } from "@/features/chat/hooks/useMessages";
import { useSession } from "@/features/chat/hooks/useSession";
import { useTypingState } from "@/features/chat/hooks/useTypingState";
import { useConfirmation } from "@/features/chat/hooks/useConfirmation";
import { useFrame, useWsStore, send } from "@/features/websocket/useWebSocket";
import { queryKeys } from "@/lib/queryKeys";
import { useOnboardingSession } from "@/features/onboarding/useOnboardingSession";
import { useSendNotice } from "@/features/websocket/useSendNotice";
import type { MessageSchema as Message, WsScreenContext as ScreenContext } from "@ze/client";

export type { PendingConfirm } from "@/features/chat/hooks/useConfirmation";

const NOT_CONNECTED_NOTICE = "Not connected. Retry when Ze reconnects.";

interface UseChatSessionOptions {
  /** Overlay chat — no history, clears when opened */
  ephemeral?: boolean;
  active?: boolean;
  context?: ScreenContext;
}

export function useChatSession(options: UseChatSessionOptions = {}) {
  const { ephemeral = false, active = true, context } = options;
  const threadId = useSession((s) => s.threadId);
  const queryClient = useQueryClient();
  const { messages: persistedMessages, upsert, edit, loadHistory, reload } = useMessages(threadId);

  const [ephemeralMessages, setEphemeralMessages] = useState<Message[]>([]);
  const [streamingText, setStreamingText] = useState<string | null>(null);
  const prevActiveRef = useRef(active);

  const isThinking = useWsStore((s) => s.isThinking);
  const setThinking = useWsStore((s) => s.setThinking);
  const isConnected = useWsStore((s) => s.isConnected);

  const { showTyping, typingText, clearTyping } = useTypingState(active);
  const { pendingConfirm, respond: respondToConfirm, clear: clearConfirm } = useConfirmation(active, ephemeral);

  const messages = ephemeral ? ephemeralMessages : persistedMessages;

  useEffect(() => {
    if (ephemeral && active && !prevActiveRef.current) {
      setEphemeralMessages([]);
    }
    prevActiveRef.current = active;
  }, [active, ephemeral]);

  useEffect(() => {
    if (!ephemeral && isConnected && active) {
      void loadHistory();
    }
  }, [ephemeral, isConnected, active, threadId, loadHistory]);

  function stopThinking() {
    setThinking(false);
    clearTyping();
    setStreamingText(null);
  }

  useFrame("message", (frame) => {
    if (!active) return;
    if (frame.message.thread_id && frame.message.thread_id !== threadId) return;

    if (frame.onboarding) {
      useOnboardingSession.getState().setSession(
        frame.onboarding.session_id,
        frame.onboarding.completed,
      );
    }

    if (ephemeral) {
      setEphemeralMessages((prev) => [...prev, frame.message]);
    } else {
      upsert(frame.message);
      if (frame.message.role === "assistant" && !frame.message.read && frame.message.id) {
        send({ type: "ack", ids: [frame.message.id] });
      }
      if (frame.message.role === "assistant") {
        void reload();
        void queryClient.invalidateQueries({ queryKey: queryKeys.sessions });
      }
    }

    stopThinking();
  });

  useFrame("edit", (frame) => {
    if (!active || ephemeral) return;
    edit(frame.id, frame.text ?? undefined, frame.components as Message["components"]);
  });

  useFrame("token", (frame) => {
    if (!active) return;
    setStreamingText((prev) => (prev ?? "") + (frame.text ?? ""));
  });

  useFrame("error", () => {
    if (!active) return;
    stopThinking();
  });

  function sendMessage(text: string): boolean {
    const trimmed = text.trim();
    if (!trimmed || isThinking) return false;

    if (ephemeral) {
      const sent = send({ type: "message", text: trimmed, context });
      if (!sent) {
        useSendNotice.getState().showNotice(NOT_CONNECTED_NOTICE);
        return false;
      }
      setThinking(true);
      return true;
    }

    const optimisticId = crypto.randomUUID();
    const sent = send({ type: "message", text: trimmed, thread_id: threadId });
    if (!sent) {
      useSendNotice.getState().showNotice(NOT_CONNECTED_NOTICE);
      return false;
    }

    upsert({
      id: optimisticId,
      role: "user",
      text: trimmed,
      components: [],
      read: true,
      created_at: new Date().toISOString(),
      thread_id: threadId,
    });

    setThinking(true);
    return true;
  }

  function resetInteraction() {
    setThinking(false);
    clearConfirm();
    clearTyping();
  }

  return {
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
  };
}
