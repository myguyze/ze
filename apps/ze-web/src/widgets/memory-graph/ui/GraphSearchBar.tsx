import { Search, X } from "lucide-react";

interface Props {
  value: string;
  onChange: (value: string) => void;
}

export function GraphSearchBar({ value, onChange }: Props) {
  return (
    <div className="relative flex items-center">
      <Search className="absolute left-2.5 w-3.5 h-3.5 text-smoke pointer-events-none" />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Search entities…"
        className="rounded-lg border border-white/10 bg-white/[0.03] pl-8 pr-7 py-1.5 text-xs text-white placeholder-smoke focus:outline-none focus:border-plum-voltage/60 w-48"
      />
      {value && (
        <button
          onClick={() => onChange("")}
          className="absolute right-2 text-smoke hover:text-white transition-colors"
        >
          <X className="w-3 h-3" />
        </button>
      )}
    </div>
  );
}
