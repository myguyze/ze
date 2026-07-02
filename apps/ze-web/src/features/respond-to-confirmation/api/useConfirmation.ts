import type { WsConfirmAction } from "@myguyze/ze-client";
import { useState } from "react";
import { useSendNotice } from "@/features/send-context-notice";
import { useFrame, useWsStore, send } from "@/shared/api";

export interface PendingConfirm {
  id: string;
  prompt: string;
  actions: WsConfirmAction[];
  threadId: string;
}

const NOT_CONNECTED_NOTICE = "Not connected. Retry when Ze reconnects.";

export function useConfirmation(active: boolean, ephemeral: boolean, threadId: string) {
  const [pendingConfirm, setPendingConfirm] = useState<PendingConfirm | null>(null);
  const setThreadThinking = useWsStore((s) => s.setThreadThinking);
  const setThreadAttention = useWsStore((s) => s.setThreadAttention);

  useFrame("confirm_request", (frame) => {
    if (ephemeral) return;
    const frameThread = frame.thread_id ?? threadId;
    if (frameThread !== threadId) {
      // Confirmation needed on another thread — set attention there
      setThreadAttention(frameThread, true);
      return;
    }
    if (!active) return;
    setThreadThinking(threadId, false);
    setPendingConfirm({ id: frame.id, prompt: frame.prompt, actions: frame.actions, threadId });
  });

  useFrame("confirm_cancel", (frame) => {
    const frameThread = frame.thread_id ?? threadId;
    if (frameThread !== threadId) return;
    if (!active || ephemeral) return;
    setPendingConfirm(null);
  });

  function respond(value: string) {
    if (!pendingConfirm) return;
    const confirm = pendingConfirm;
    setPendingConfirm(null);

    const isCheckpoint = value === "approve" || value === "deny";
    const sent = isCheckpoint
      ? send({ type: "confirm", id: confirm.id, choice: value, thread_id: confirm.threadId })
      : send({ type: "action", payload: value, thread_id: confirm.threadId });

    if (!sent) {
      setPendingConfirm(confirm);
      useSendNotice.getState().showNotice(NOT_CONNECTED_NOTICE);
      return;
    }

    if (isCheckpoint && value === "approve") {
      setThreadThinking(threadId, true);
    }
  }

  function clear() {
    setPendingConfirm(null);
  }

  return { pendingConfirm, respond, clear };
}
