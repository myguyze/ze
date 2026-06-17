import { type ConnectionsComponent as T, type ConnectionItem } from "./types";

const RELATION_LABELS: Record<string, string> = {
  pattern:      "Pattern",
  causal_guess: "Possible link",
  tension:      "Tension",
  convergence:  "Convergence",
};

function Connection({ item }: { item: ConnectionItem }) {
  const rel = RELATION_LABELS[item.relation] ?? item.relation;
  return (
    <div className="px-4 py-3 border-b border-white/5 last:border-0">
      <div className="flex items-start gap-2 mb-1">
        <span className="flex-shrink-0 mt-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium tracking-wide uppercase border border-[#8052ff]/40 text-[#8052ff]">
          {rel}
        </span>
        <p className="text-sm text-white leading-snug">{item.summary}</p>
      </div>
      <p className="text-xs text-[#9a9a9a] leading-relaxed mb-2">{item.narrative}</p>
      {item.evidence && item.evidence.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {item.evidence.map((ev, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-white/5 text-[11px] text-[#9a9a9a]"
            >
              {ev.label}
              {ev.date && <span className="text-white/30">· {ev.date}</span>}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function ConnectionsComponent({ data }: { data: T }) {
  return (
    <div className="mt-2 rounded-[24px] border border-[#8052ff]/20 overflow-hidden">
      <p className="px-4 py-2 text-xs font-semibold tracking-widest uppercase text-[#8052ff] border-b border-[#8052ff]/20">
        {data.title ?? "Connected to your history"}
      </p>
      {data.connections.map((item, i) => (
        <Connection key={i} item={item} />
      ))}
    </div>
  );
}
