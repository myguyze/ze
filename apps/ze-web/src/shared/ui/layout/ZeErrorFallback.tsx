import { Link } from "react-router-dom";
import { pickZeErrorCopy, seedFromError } from "./ze-error-copy";

interface ZeErrorFallbackProps {
  error?: Error;
  onReset?: () => void;
}

export function ZeErrorFallback({ error, onReset }: ZeErrorFallbackProps) {
  const { headline, subtext } = pickZeErrorCopy(seedFromError(error));

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-black px-6 py-16 text-center text-white">
      <div className="flex flex-col items-center gap-4">
        <div className="h-10 w-10 rounded-full bg-plum-voltage shadow-[0_0_32px_rgba(139,92,246,0.35)]" />
        <p className="text-[40px] font-extralight tracking-tight leading-none select-none">Ze</p>
      </div>

      <div className="max-w-md space-y-2">
        <p className="text-lg text-white">{headline}</p>
        <p className="text-sm text-smoke">{subtext}</p>
      </div>

      <div className="flex flex-wrap items-center justify-center gap-3">
        {onReset && (
          <button
            type="button"
            onClick={onReset}
            className="rounded-pill border border-plum-voltage/50 px-4 py-2 text-sm text-plum-voltage transition-colors hover:border-plum-voltage hover:text-white"
          >
            Try again
          </button>
        )}
        <Link
          to="/"
          className="rounded-pill px-4 py-2 text-sm text-smoke transition-colors hover:text-white"
        >
          Back to chat
        </Link>
      </div>

      {import.meta.env.DEV && error && (
        <details className="mt-4 max-w-xl text-left">
          <summary className="cursor-pointer text-xs text-smoke/70 hover:text-smoke">
            Developer details
          </summary>
          <pre className="mt-3 overflow-x-auto rounded-lg border border-white/10 bg-white/[0.03] p-4 text-left text-xs text-smoke/80 whitespace-pre-wrap">
            {error.message}
            {error.stack ? `\n\n${error.stack}` : ""}
          </pre>
        </details>
      )}
    </div>
  );
}
