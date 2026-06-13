import { type MetricComponent as T } from "./types";

export function MetricComponent({ data }: { data: T }) {
  return (
    <div className="mt-2 p-4 rounded-[24px] border border-white/10 inline-block min-w-[140px]">
      <p className="text-[48px] font-extralight leading-none tracking-tight text-white">
        {data.value}
      </p>
      <p className="mt-1 text-xs tracking-wide text-[#9a9a9a]">{data.label}</p>
      {data.trend && (
        <span className="mt-2 inline-block px-2 py-0.5 rounded-full border border-[#ffb829] text-[#ffb829] text-xs">
          {data.trend}
        </span>
      )}
      {data.note && (
        <p className="mt-1 text-xs text-[#9a9a9a]">{data.note}</p>
      )}
    </div>
  );
}
