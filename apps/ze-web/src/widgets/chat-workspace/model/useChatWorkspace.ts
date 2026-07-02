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
  threadId?: string;
}

export function useChatWorkspace(options: UseChatWorkspaceOptions = {}) {
  const { ephemeral = false, active = true, context, threadId: threadIdOverride } = options;
  const sessionThreadId = useSession((s) => s.threadId);
  const threadId = threadIdOverride ?? sessionThreadId;
  const queryClient = useQueryClient();
  const { messages: persistedMessages, upsert, edit, loadHistory, reload } = useMessages(threadId);

  const [ephemeralMessages, setEphemeralMessages] = useState<Message[]>([]);
  const [streamingText, setStreamingText] = useState<string | null>(null);
  const [showTyping, setShowTyping] = useState(false);
  const [typingText, setTypingText] = useState<string | null>(null);
  const typingTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const prevActiveRef = useRef(active);

  const isThinking = useWsStore((s) => s.thinkingThreads[threadId] ?? false);
  const setThreadThinking = useWsStore((s) => s.setThreadThinking);
  const setThreadAttention = useWsStore((s) => s.setThreadAttention);
  const isConnected = useWsStore((s) => s.isConnected);

  const { pendingConfirm, respond: respondToConfirm, clear: clearConfirm } = useConfirmation(
    active,
    ephemeral,
    threadId,
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
    const frameThread = frame.thread_id ?? null;
    if (frameThread && frameThread !== threadId) {
      // Another thread is thinking — mark it busy in global store.
      // The backend stores the user message before sending typing, so the
      // session exists in the DB now — invalidate the sessions list.
      setThreadThinking(frameThread, true);
      void queryClient.invalidateQueries({ queryKey: queryKeys.sessions });
      return;
    }
    // Typing for our own thread.
    // Session is guaranteed to exist in the DB at this point.
    void queryClient.invalidateQueries({ queryKey: queryKeys.sessions });
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
    setThreadThinking(threadId, false);
    clearTyping();
    setStreamingText(null);
  }

  useFrame("message", (frame) => {
    const frameThread = frame.message.thread_id ?? null;

    if (frameThread && frameThread !== threadId) {
      // Message arrived for a different thread — clear its thinking and signal attention.
      setThreadThinking(frameThread, false);
      if (frame.message.role === "assistant") {
        // Only set attention if the session isn't the one the user is currently viewing.
        // Read from the session store directly (outside React) to get the canonical
        // active thread, not the overlay's threadId.
        const activeThread = useSession.getState().threadId;
        if (frameThread !== activeThread) {
          setThreadAttention(frameThread, true);
        }
        void queryClient.invalidateQueries({ queryKey: queryKeys.sessions });
      }
      return;
    }

    // Message for our own thread — ensure any stale attention is cleared.
    setThreadAttention(threadId, false);

    if (!active) return;

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
    const frameThread = frame.thread_id ?? null;
    if (frameThread && frameThread !== threadId) return;
    if (!active) return;
    setStreamingText((prev) => (prev ?? "") + (frame.text ?? ""));
  });

  useFrame("error", (frame) => {
    const frameThread = frame.thread_id ?? null;
    if (frameThread && frameThread !== threadId) {
      setThreadThinking(frameThread, false);
      return;
    }
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
      setThreadThinking(threadId, true);
      return true;
    }

    const sent = send({ type: "message", text: trimmed, thread_id: threadId, context });
    if (!sent) {
      useSendNotice.getState().showNotice(NOT_CONNECTED_NOTICE);
      return false;
    }

    upsert({
      id: crypto.randomUUID(),
      role: "user",
      text: trimmed,
      components: [],
      read: true,
      created_at: new Date().toISOString(),
      thread_id: threadId,
    });

    setThreadThinking(threadId, true);
    return true;
  }

  function resetInteraction() {
    setThreadThinking(threadId, false);
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
