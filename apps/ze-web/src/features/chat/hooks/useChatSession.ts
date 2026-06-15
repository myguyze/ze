import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useMessages } from "@/features/chat/hooks/useMessages";
import { useSession } from "@/features/chat/hooks/useSession";
import { useFrame, useWsStore, send } from "@/features/websocket/useWebSocket";
import { type ConfirmAction, type Message, type ScreenContext } from "@/features/websocket/protocol";

export interface PendingConfirm {
  id: string;
  prompt: string;
  actions: ConfirmAction[];
}

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
  const [showTyping, setShowTyping] = useState(false);
  const [pendingConfirm, setPendingConfirm] = useState<PendingConfirm | null>(null);
  const typingTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const prevActiveRef = useRef(active);

  const isThinking = useWsStore((s) => s.isThinking);
  const setThinking = useWsStore((s) => s.setThinking);
  const isConnected = useWsStore((s) => s.isConnected);

  const messages = ephemeral ? ephemeralMessages : persistedMessages;

  useEffect(() => {
    if (ephemeral && active && !prevActiveRef.current) {
      setEphemeralMessages([]);
      setShowTyping(false);
    }
    prevActiveRef.current = active;
  }, [active, ephemeral]);

  useEffect(() => {
    if (!ephemeral && isConnected && active) {
      void loadHistory();
    }
  }, [ephemeral, isConnected, active, threadId, loadHistory]);

  function clearTyping() {
    setShowTyping(false);
    clearTimeout(typingTimer.current);
  }

  function stopThinking() {
    setThinking(false);
    clearTyping();
  }

  useFrame("message", (frame) => {
    if (!active) return;
    if (frame.message.thread_id && frame.message.thread_id !== threadId) return;

    if (ephemeral) {
      setEphemeralMessages((prev) => [...prev, frame.message]);
    } else {
      upsert(frame.message);
      if (frame.message.role === "assistant" && !frame.message.read) {
        send({ type: "ack", ids: [frame.message.id] });
      }
      if (frame.message.role === "assistant") {
        void reload();
        void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      }
    }

    stopThinking();
  });

  useFrame("edit", (frame) => {
    if (!active || ephemeral) return;
    edit(frame.id, frame.text, frame.components);
  });

  useFrame("typing", () => {
    if (!active) return;
    setShowTyping(true);
    clearTimeout(typingTimer.current);
    typingTimer.current = setTimeout(() => setShowTyping(false), 3_000);
  });

  useFrame("confirm_request", (frame) => {
    if (!active || ephemeral) return;
    setThinking(false);
    clearTyping();
    setPendingConfirm({ id: frame.id, prompt: frame.prompt, actions: frame.actions });
  });

  useFrame("confirm_cancel", () => {
    if (!active || ephemeral) return;
    setPendingConfirm(null);
  });

  useFrame("error", () => {
    if (!active) return;
    stopThinking();
  });

  function sendMessage(text: string): boolean {
    const trimmed = text.trim();
    if (!trimmed || isThinking) return false;

    setThinking(true);

    if (ephemeral) {
      send({ type: "message", text: trimmed, context });
    } else {
      upsert({
        id: crypto.randomUUID(),
        role: "user",
        text: trimmed,
        components: [],
        read: true,
        created_at: new Date().toISOString(),
        thread_id: threadId,
      });
      send({ type: "message", text: trimmed, thread_id: threadId });
    }

    return true;
  }

  function respondToConfirm(choice: "approve" | "deny") {
    if (!pendingConfirm) return;
    const { id } = pendingConfirm;
    setPendingConfirm(null);
    send({ type: "confirm", id, choice });
    if (choice === "approve") {
      setThinking(true);
    }
  }

  function resetInteraction() {
    setThinking(false);
    setPendingConfirm(null);
    clearTyping();
  }

  return {
    threadId,
    messages,
    showTyping,
    isThinking,
    isConnected,
    pendingConfirm,
    sendMessage,
    respondToConfirm,
    resetInteraction,
  };
}
