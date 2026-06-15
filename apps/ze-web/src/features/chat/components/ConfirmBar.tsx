import { type ConfirmAction } from "@/features/websocket/protocol";
import { cn } from "@/lib/cn";

interface ConfirmBarProps {
  prompt: string;
  actions: ConfirmAction[];
  onConfirm: (choice: "approve" | "deny") => void;
}

export function ConfirmBar({ prompt, actions, onConfirm }: ConfirmBarProps) {
  return (
    <div className="relative z-10 mx-4 mb-2 p-4 rounded-[24px] border border-[#8052ff]/40 bg-[#8052ff]/5">
      <p className="text-sm text-white mb-3">{prompt}</p>
      <div className="flex flex-wrap gap-2">
        {actions.map((action) => (
          <button
            key={action.value}
            onClick={() => onConfirm(action.value as "approve" | "deny")}
            className={cn(
              "px-4 py-2 rounded-[24px] text-xs font-semibold tracking-wide transition-opacity",
              action.style === "primary" || !action.style
                ? "bg-[#8052ff] text-white"
                : action.style === "danger"
                  ? "border border-[#ffb829] text-[#ffb829]"
                  : "border border-white/20 text-white",
            )}
          >
            {action.label}
          </button>
        ))}
      </div>
    </div>
  );
}
