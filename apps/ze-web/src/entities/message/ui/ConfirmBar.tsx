import type { WsConfirmAction } from "@ze/client";
import { cn } from "@/shared/lib/cn";

interface ConfirmBarProps {
  prompt: string;
  actions: WsConfirmAction[];
  onConfirm: (choice: "approve" | "deny") => void;
}

export function ConfirmBar({ prompt, actions, onConfirm }: ConfirmBarProps) {
  return (
    <div className="relative z-10 mx-4 mb-2 p-4 rounded-pill border border-plum-voltage/40 bg-plum-voltage/5">
      <p className="text-sm text-white mb-3">{prompt}</p>
      <div className="flex flex-wrap gap-2">
        {actions.map((action) => (
          <button
            key={action.value}
            onClick={() => onConfirm(action.value)}
            className={cn(
              "px-4 py-2 rounded-pill text-xs font-semibold tracking-wide transition-opacity",
              action.style === "primary" || !action.style
                ? "bg-plum-voltage text-white"
                : action.style === "danger"
                  ? "border border-amber-spark text-amber-spark"
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
