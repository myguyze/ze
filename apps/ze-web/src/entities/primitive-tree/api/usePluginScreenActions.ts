import type { PrimitiveRendererActions } from "@ze/ui/react";
import { useMemo } from "react";
import { useSendNotice } from "@/features/send-context-notice";
import { useOnboardingSession } from "@/entities/onboarding-session";
import { useSession } from "@/entities/session";
import { send } from "@/shared/api";

export function usePluginScreenActions(onRestAction?: () => void): PrimitiveRendererActions {
  const sessionId = useOnboardingSession((s) => s.sessionId);
  const completed = useOnboardingSession((s) => s.completed);
  const threadId = useSession((s) => s.threadId);
  const showNotice = useSendNotice((s) => s.showNotice);

  return useMemo(
    () => ({
      onButtonAction: (action: string) => {
        if (action.startsWith("rest:")) {
          onRestAction?.();
          return;
        }
        const text = action.startsWith("msg:") ? action.slice(4) : action;
        return send({ type: "message", text, thread_id: threadId });
      },
      onFormSubmit: (formId: string, values: Record<string, string>) => {
        if (sessionId && !completed && formId) {
          return send({
            type: "component_submit",
            session_id: sessionId,
            step_id: formId,
            values,
          });
        }
        return send({ type: "message", text: `[form] ${JSON.stringify(values)}`, thread_id: threadId });
      },
      onDisconnected: () => {
        showNotice("Not connected. Retry when Ze reconnects.");
      },
    }),
    [completed, onRestAction, sessionId, showNotice, threadId],
  );
}
