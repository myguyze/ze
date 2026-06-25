export function TypingIndicator({ text }: { text?: string | null }) {
  return (
    <div className="flex items-start gap-2">
      <div className="w-6 h-6 rounded-full bg-plum-voltage/20 flex items-center justify-center flex-shrink-0">
        <span className="text-[10px] text-plum-voltage font-semibold">Z</span>
      </div>
      <div className="px-4 py-2.5 rounded-[20px] border border-white/10 text-sm text-smoke">
        {text ?? (
          <span className="inline-flex gap-1">
            <span className="animate-pulse">·</span>
            <span className="animate-pulse delay-100">·</span>
            <span className="animate-pulse delay-200">·</span>
          </span>
        )}
      </div>
    </div>
  );
}
