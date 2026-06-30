import type { MemoryChunkTraceResponse } from "@myguyze/ze-client";

const SOURCE_COLORS: Record<string, string> = {
  fact: "text-emerald-400",
  episode: "text-sky-400",
  profile: "text-amber-400",
};

interface MemoryChunkListProps {
  chunks: MemoryChunkTraceResponse[];
}

export function MemoryChunkList({ chunks }: MemoryChunkListProps) {
  if (chunks.length === 0) {
    return <p className="text-xs text-smoke/60 italic">No memory retrieved</p>;
  }

  return (
    <ul className="space-y-1.5">
      {chunks.map((chunk, i) => (
        <li key={i} className="flex items-start gap-2 text-xs">
          <span
            className={`flex-shrink-0 font-mono text-[10px] mt-0.5 ${SOURCE_COLORS[chunk.source] ?? "text-smoke"}`}
          >
            [{chunk.source} {(chunk.score * 100).toFixed(0)}%]
          </span>
          <span className="text-white/80 leading-relaxed line-clamp-2">{chunk.text}</span>
        </li>
      ))}
    </ul>
  );
}
