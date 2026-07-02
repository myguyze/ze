import { Search } from "lucide-react";

interface SessionSearchInputProps {
  value: string;
  onChange: (value: string) => void;
}

export function SessionSearchInput({ value, onChange }: SessionSearchInputProps) {
  return (
    <div className="relative px-3 pt-2 pb-1">
      <Search className="pointer-events-none absolute left-6 top-1/2 size-3.5 -translate-y-1/2 text-smoke/60" />
      <input
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Search conversations…"
        aria-label="Search conversations"
        className="h-9 w-full rounded-pill border border-white/10 bg-white/[0.03] pl-9 pr-3 text-sm text-white placeholder:text-smoke/60 focus:border-plum-voltage/40 focus:outline-none"
      />
    </div>
  );
}
