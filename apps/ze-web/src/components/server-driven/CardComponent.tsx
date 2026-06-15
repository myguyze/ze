import { type CardComponent as T } from "./types";
import { cn } from "@/lib/cn";

const borderColor = {
  info:    "border-l-[#8052ff]",
  warning: "border-l-[#ffb829]",
  success: "border-l-[#15846e]",
  error:   "border-l-red-500",
} as const;

export function CardComponent({ data }: { data: T }) {
  const style = data.style ?? "info";
  return (
    <div
      className={cn(
        "mt-2 p-4 rounded-[24px] border border-white/10 border-l-4",
        borderColor[style],
      )}
    >
      {data.title && (
        <p className="text-xs font-semibold tracking-wide text-[#9a9a9a] mb-1 uppercase">
          {data.title}
        </p>
      )}
      <p className="text-sm text-white">{data.body}</p>
    </div>
  );
}
