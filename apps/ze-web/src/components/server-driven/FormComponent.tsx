import { useState, type FormEvent } from "react";
import { send } from "@/features/websocket/useWebSocket";
import { useSendNotice } from "@/features/websocket/useSendNotice";
import { useOnboardingSession } from "@/features/onboarding/useOnboardingSession";
import { useSession } from "@/features/chat/hooks/useSession";
import { type FormComponent as T } from "./types";

const NOT_CONNECTED_NOTICE = "Not connected. Retry when Ze reconnects.";

export function FormComponent({ data }: { data: T }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [submitted, setSubmitted] = useState(false);
  const sessionId = useOnboardingSession((s) => s.sessionId);
  const completed = useOnboardingSession((s) => s.completed);
  const threadId = useSession((s) => s.threadId);
  const stepId = data.id;

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (submitted) return;
    setSubmitted(true);

    let sent = false;
    if (sessionId && !completed && stepId) {
      sent = send({
        type: "component_submit",
        session_id: sessionId,
        step_id: stepId,
        values,
      });
    } else if (stepId) {
      sent = send({
        type: "component_submit",
        step_id: stepId,
        values,
        thread_id: threadId,
      });
    } else {
      sent = send({ type: "message", text: `[form] ${JSON.stringify(values)}` });
    }

    if (!sent) {
      setSubmitted(false);
      useSendNotice.getState().showNotice(NOT_CONNECTED_NOTICE);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mt-2 p-4 rounded-[24px] border border-white/10 space-y-3">
      <p className="text-sm font-semibold text-white">{data.title}</p>
      {data.fields.map((field) => (
        <div key={field.id}>
          <label className="block text-xs text-[#9a9a9a] mb-1 tracking-wide">
            {field.label}
          </label>
          {field.field_type === "select" ? (
            <select
              value={values[field.id] ?? ""}
              onChange={(e) => setValues((v) => ({ ...v, [field.id]: e.target.value }))}
              disabled={submitted}
              className="w-full bg-transparent border border-white/20 rounded-[24px] px-3 py-2 text-sm text-white focus:outline-none focus:border-[#8052ff] disabled:opacity-40"
            >
              <option value="">Select…</option>
              {field.options?.map((o) => (
                <option key={o} value={o} className="bg-black">
                  {o}
                </option>
              ))}
            </select>
          ) : (
            <input
              type={field.field_type}
              placeholder={field.placeholder}
              value={values[field.id] ?? ""}
              onChange={(e) => setValues((v) => ({ ...v, [field.id]: e.target.value }))}
              disabled={submitted}
              className="w-full bg-transparent border border-white/20 rounded-[24px] px-3 py-2 text-sm text-white placeholder-[#9a9a9a] focus:outline-none focus:border-[#8052ff] disabled:opacity-40"
            />
          )}
        </div>
      ))}
      <button
        type="submit"
        disabled={submitted}
        className="w-full py-2 rounded-[24px] bg-[#8052ff] text-white text-xs font-semibold tracking-widest uppercase disabled:opacity-40 transition-opacity"
      >
        {submitted ? "Submitted" : "Submit"}
      </button>
    </form>
  );
}
