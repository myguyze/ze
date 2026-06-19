import { TypingDots } from "@/lib/aceternity/text-generate-effect";

interface TypingIndicatorProps {
  text?: string | null;
}

export function TypingIndicator({ text }: TypingIndicatorProps) {
  return (
    <div className="flex items-start gap-2">
      <div className="w-6 h-6 rounded-full bg-plum-voltage/20 flex items-center justify-center flex-shrink-0 mt-1">
        <span className="text-[10px] text-plum-voltage font-semibold">Z</span>
      </div>
      <div className="px-4 py-3 rounded-pill border border-white/10 inline-block">
        {text ? (
          <span className="text-sm text-white/50">{text}</span>
        ) : (
          <TypingDots />
        )}
      </div>
    </div>
  );
}
