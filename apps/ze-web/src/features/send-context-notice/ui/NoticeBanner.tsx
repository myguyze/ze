import { X } from "lucide-react";
import { useSendNotice } from "@/features/send-context-notice";

export function NoticeBanner() {
  const notice = useSendNotice((s) => s.notice);
  const clearNotice = useSendNotice((s) => s.clearNotice);

  if (!notice) return null;

  return (
    <div className="mx-4 mt-3 flex items-center justify-between gap-3 px-4 py-2 rounded-pill border border-amber-spark/40 text-amber-spark text-xs">
      <span className="flex items-center gap-2 min-w-0">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-spark flex-shrink-0" />
        <span className="truncate">{notice}</span>
      </span>
      <button
        type="button"
        onClick={clearNotice}
        className="text-amber-spark hover:text-white transition-colors flex-shrink-0"
        aria-label="Dismiss"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
