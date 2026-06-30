import type { PrimitiveRendererActions } from "@myguyze/ze-ui/react";
import { useMemo } from "react";
import { useSendNotice } from "@/features/send-context-notice";
import { useOnboardingSession } from "@/entities/onboarding-session";
import { useSession } from "@/entities/session";
import { send } from "@/shared/api";

export function usePrimitiveRendererActions(): PrimitiveRendererActions {
  const sessionId = useOnboardingSession((s) => s.sessionId);
  const completed = useOnboardingSession((s) => s.completed);
  const threadId = useSession((s) => s.threadId);
  const showNotice = useSendNotice((s) => s.showNotice);

  return useMemo(
    () => ({
      onButtonAction: (action: string) => {
        return send({ type: "message", text: action, thread_id: threadId });
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
        if (formId) {
          return send({
            type: "component_submit",
            step_id: formId,
            values,
            thread_id: threadId,
          });
        }
        return send({ type: "message", text: `[form] ${JSON.stringify(values)}` });
      },
      onDisconnected: () => {
        showNotice("Not connected. Retry when Ze reconnects.");
      },
    }),
    [completed, sessionId, showNotice, threadId],
  );
}
