import { type ListComponent as T } from "./types";

export function ListComponent({ data }: { data: T }) {
  return (
    <div className="mt-2 rounded-[24px] border border-white/10 overflow-hidden">
      {data.title && (
        <p className="px-4 py-2 text-xs font-semibold tracking-widest uppercase text-[#9a9a9a] border-b border-white/10">
          {data.title}
        </p>
      )}
      {data.items.map((item, i) => (
        <div
          key={i}
          className="flex items-center justify-between px-4 py-3 border-b border-white/5 last:border-0"
        >
          <div>
            <p className="text-sm text-white">{item.text}</p>
            {item.subtext && (
              <p className="text-xs text-[#9a9a9a] mt-0.5">{item.subtext}</p>
            )}
          </div>
          {item.status && (
            <span className="ml-3 flex-shrink-0 px-2 py-0.5 rounded-full border border-[#8052ff]/50 text-[#8052ff] text-xs">
              {item.status}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
