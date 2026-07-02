import { Search, X } from "lucide-react";
import { cn } from "@/shared/lib/cn";

interface SearchBarProps {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  className?: string;
}

export function SearchBar({ value, onChange, placeholder = "Search…", className }: SearchBarProps) {
  return (
    <div className={cn("relative flex items-center", className)}>
      <Search className="absolute left-3 size-4 text-smoke pointer-events-none" />
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="h-9 w-full rounded-pill border border-white/10 bg-white/[0.03] pl-9 pr-9 text-sm text-white placeholder:text-smoke focus:outline-none focus:border-plum-voltage/50 transition-colors"
      />
      {value && (
        <button
          onClick={() => onChange("")}
          className="absolute right-3 text-smoke hover:text-white transition-colors"
        >
          <X className="size-3.5" />
        </button>
      )}
    </div>
  );
}
