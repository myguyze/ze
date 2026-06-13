import { useState } from "react";
import { send } from "@/ws/useWebSocket";
import { type ConfirmComponent as T } from "./types";
import { cn } from "@/lib/cn";

export function ConfirmComponent({ data }: { data: T }) {
  const [chosen, setChosen] = useState<string | null>(null);

  function handleTap(value: string) {
    if (chosen) return;
    setChosen(value);
    send({ type: "message", text: value });
  }

  return (
    <div className="mt-2 p-4 rounded-[24px] border border-white/10">
      <p className="text-sm text-white mb-3">{data.prompt}</p>
      <div className="flex flex-wrap gap-2">
        {data.actions.map((action) => (
          <button
            key={action.value}
            onClick={() => handleTap(action.value)}
            disabled={!!chosen}
            className={cn(
              "px-4 py-2 rounded-[24px] text-xs font-semibold tracking-wide transition-opacity disabled:opacity-40",
              chosen === action.value && "opacity-100",
              action.style === "primary" || !action.style
                ? "bg-[#8052ff] text-white"
                : action.style === "danger"
                  ? "border border-[#ffb829] text-[#ffb829]"
                  : "border border-white/20 text-white",
            )}
          >
            {chosen === action.value ? `✓ ${action.label}` : action.label}
          </button>
        ))}
      </div>
    </div>
  );
}
