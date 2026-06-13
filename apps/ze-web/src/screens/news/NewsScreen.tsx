import { Newspaper } from "lucide-react";
import { FloatingButton } from "@/overlay/FloatingButton";

export function NewsScreen() {
  return (
    <div className="px-4 py-8 flex flex-col items-center justify-center min-h-[60vh] gap-4 text-center">
      <Newspaper className="w-8 h-8 text-[#9a9a9a]" />
      <p className="text-xs font-semibold tracking-widest uppercase text-[#9a9a9a]">Coming soon</p>
      <p className="text-2xl font-extralight text-white">News</p>
      <p className="text-sm text-[#9a9a9a] max-w-xs">
        Personalised news is on the roadmap. For now, ask Ze to search for news on any topic.
      </p>
      <FloatingButton screen="news" />
    </div>
  );
}
