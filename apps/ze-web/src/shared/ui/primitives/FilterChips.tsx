import { cn } from "@/shared/lib/cn";

export interface FilterOption<T extends string = string> {
  label: string;
  value: T;
}

interface FilterChipsProps<T extends string> {
  options: FilterOption<T>[];
  value: T;
  onChange: (v: T) => void;
  className?: string;
}

export function FilterChips<T extends string>({ options, value, onChange, className }: FilterChipsProps<T>) {
  return (
    <div className={cn("flex items-center gap-1.5", className)}>
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={cn(
            "px-3 py-1 rounded-full text-xs font-medium transition-colors border",
            value === opt.value
              ? "bg-plum-voltage/20 border-plum-voltage/50 text-plum-voltage"
              : "bg-transparent border-white/10 text-smoke hover:border-white/20 hover:text-white",
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
