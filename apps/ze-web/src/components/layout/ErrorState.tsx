import { AlertCircle } from "lucide-react";

interface ErrorStateProps {
  message: string;
  detail?: string;
  onRetry?: () => void;
}

export function ErrorState({ message, detail, onRetry }: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
      <AlertCircle className="w-8 h-8 text-[#ffb829]" />
      <p className="text-sm text-[#9a9a9a]">{message}</p>
      {detail && <p className="text-xs text-[#9a9a9a] max-w-xs">{detail}</p>}
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="text-xs text-[#8052ff] underline hover:text-white transition-colors"
        >
          Retry
        </button>
      )}
    </div>
  );
}
