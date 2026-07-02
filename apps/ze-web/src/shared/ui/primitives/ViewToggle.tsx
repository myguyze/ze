import { LayoutList, LayoutGrid } from "lucide-react";
import { cn } from "@/shared/lib/cn";

export type ViewMode = "list" | "grid";

interface ViewToggleProps {
  value: ViewMode;
  onChange: (v: ViewMode) => void;
  className?: string;
}

export function ViewToggle({ value, onChange, className }: ViewToggleProps) {
  return (
    <div className={cn("flex items-center gap-0.5 rounded-pill border border-white/10 p-0.5", className)}>
      {(["list", "grid"] as const).map((mode) => {
        const Icon = mode === "list" ? LayoutList : LayoutGrid;
        return (
          <button
            key={mode}
            onClick={() => onChange(mode)}
            className={cn(
              "flex items-center justify-center size-7 rounded-full transition-colors",
              value === mode
                ? "bg-white/10 text-white"
                : "text-smoke hover:text-white",
            )}
          >
            <Icon className="size-3.5" />
          </button>
        );
      })}
    </div>
  );
}
