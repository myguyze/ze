import { useState, type FormEvent } from "react";
import { send } from "@/features/websocket/useWebSocket";
import { type FormComponent as T } from "./types";

export function FormComponent({ data }: { data: T }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [submitted, setSubmitted] = useState(false);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (submitted) return;
    setSubmitted(true);
    send({ type: "message", text: `[form] ${JSON.stringify(values)}` });
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
