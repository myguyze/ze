import { useQueryClient } from "@tanstack/react-query";
import type { MessageSchema as Message, WsScreenContext as ScreenContext } from "@myguyze/ze-client";
import { useEffect, useRef, useState } from "react";
import { useMessages } from "@/features/load-chat-history";
import { useConfirmation } from "@/features/respond-to-confirmation";
import { useSendNotice } from "@/features/send-context-notice";
import { useOnboardingSession } from "@/entities/onboarding-session";
import { useSession } from "@/entities/session";
import { useFrame, useWsStore, send } from "@/shared/api";
import { queryKeys } from "@/shared/lib";

const NOT_CONNECTED_NOTICE = "Not connected. Retry when Ze reconnects.";

interface UseChatWorkspaceOptions {
  ephemeral?: boolean;
  active?: boolean;
  context?: ScreenContext;
}

export function useChatWorkspace(options: UseChatWorkspaceOptions = {}) {
  const { ephemeral = false, active = true, context } = options;
  const threadId = useSession((s) => s.threadId);
  const queryClient = useQueryClient();
  const { messages: persistedMessages, upsert, edit, loadHistory, reload } = useMessages(threadId);

  const [ephemeralMessages, setEphemeralMessages] = useState<Message[]>([]);
  const [streamingText, setStreamingText] = useState<string | null>(null);
  const [showTyping, setShowTyping] = useState(false);
  const [typingText, setTypingText] = useState<string | null>(null);
  const typingTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const prevActiveRef = useRef(active);

  const isThinking = useWsStore((s) => s.isThinking);
  const setThinking = useWsStore((s) => s.setThinking);
  const isConnected = useWsStore((s) => s.isConnected);

  const { pendingConfirm, respond: respondToConfirm, clear: clearConfirm } = useConfirmation(
    active,
    ephemeral,
  );

  const messages = ephemeral ? ephemeralMessages : persistedMessages;

  function clearTyping() {
    setShowTyping(false);
    setTypingText(null);
    clearTimeout(typingTimer.current);
  }

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
