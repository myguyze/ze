import { ArrowUpDown } from "lucide-react";
import { cn } from "@/shared/lib/cn";

export interface SortOption<T extends string = string> {
  label: string;
  value: T;
}

interface SortSelectProps<T extends string> {
  options: SortOption<T>[];
  value: T;
  onChange: (v: T) => void;
  className?: string;
}

export function SortSelect<T extends string>({ options, value, onChange, className }: SortSelectProps<T>) {
  return (
    <div className={cn("relative flex items-center", className)}>
      <ArrowUpDown className="absolute left-3 size-3.5 text-smoke pointer-events-none" />
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
        className="h-9 appearance-none rounded-pill border border-white/10 bg-white/[0.03] pl-8 pr-8 text-sm text-white focus:outline-none focus:border-plum-voltage/50 transition-colors cursor-pointer"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value} className="bg-black text-white">
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}
