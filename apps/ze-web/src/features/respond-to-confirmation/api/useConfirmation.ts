import type { WsConfirmAction } from "@ze/client";
import { useState } from "react";
import { useSendNotice } from "@/features/send-context-notice";
import { useFrame, useWsStore, send } from "@/shared/api";

export interface PendingConfirm {
  id: string;
  prompt: string;
  actions: WsConfirmAction[];
}

const NOT_CONNECTED_NOTICE = "Not connected. Retry when Ze reconnects.";

export function useConfirmation(active: boolean, ephemeral: boolean) {
  const [pendingConfirm, setPendingConfirm] = useState<PendingConfirm | null>(null);
  const setThinking = useWsStore((s) => s.setThinking);

  useFrame("confirm_request", (frame) => {
    if (!active || ephemeral) return;
    setThinking(false);
    setPendingConfirm({ id: frame.id, prompt: frame.prompt, actions: frame.actions });
  });

  useFrame("confirm_cancel", () => {
    if (!active || ephemeral) return;
    setPendingConfirm(null);
  });

  function respond(choice: "approve" | "deny") {
    if (!pendingConfirm) return;
    const confirm = pendingConfirm;
    setPendingConfirm(null);

    const sent = send({ type: "confirm", id: confirm.id, choice });
    if (!sent) {
      setPendingConfirm(confirm);
      useSendNotice.getState().showNotice(NOT_CONNECTED_NOTICE);
      return;
    }

    if (choice === "approve") {
      setThinking(true);
    }
  }

  function clear() {
    setPendingConfirm(null);
  }

  return { pendingConfirm, respond, clear };
}
