import type { SessionSchema } from "@myguyze/ze-client";
import { MessageSquare } from "lucide-react";
import { cn } from "@/shared/lib/cn";
import { formatRelative } from "../lib/formatRelative";
import { MarkdownPreview } from "./MarkdownPreview";

interface SessionRowProps {
  session: SessionSchema;
  active?: boolean;
  onSelect: () => void;
}

function SessionRowContent({ session }: { session: SessionSchema }) {
  const title = session.title;
  const preview = session.preview;

  if (title) {
    return (
      <>
        <p className="text-sm font-medium text-white leading-snug line-clamp-1">{title}</p>
        {preview && preview !== title && (
          <div className="mt-1 text-xs leading-relaxed text-smoke line-clamp-2">
            <MarkdownPreview>{preview}</MarkdownPreview>
          </div>
        )}
      </>
    );
  }

  if (preview) {
    return (
      <div className="text-sm leading-relaxed text-white line-clamp-2">
        <MarkdownPreview>{preview}</MarkdownPreview>
      </div>
    );
  }

  return <p className="text-sm font-medium text-white">Untitled chat</p>;
}

export function SessionRow({ session, active = false, onSelect }: SessionRowProps) {
  const label = session.title ?? session.preview ?? "Untitled chat";

  return (
    <button
      type="button"
      onClick={onSelect}
      title={`${label} · ${formatRelative(session.last_active_at)}`}
      className={cn(
        "group w-full text-left rounded-pill border px-3.5 py-3 transition-colors",
        active
          ? "border-plum-voltage/30 bg-plum-voltage/10"
          : "border-white/10 bg-white/[0.02] hover:border-white/20 hover:bg-white/[0.04]",
      )}
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            "mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full border",
            active
              ? "border-plum-voltage/30 bg-plum-voltage/15"
              : "border-white/10 bg-white/[0.03] group-hover:border-white/20",
          )}
        >
          <MessageSquare
            className={cn("size-3.5", active ? "text-plum-voltage" : "text-smoke group-hover:text-white/80")}
          />
        </div>

        <div className="min-w-0 flex-1">
          <SessionRowContent session={session} />
          <p className="mt-1.5 text-[10px] text-smoke/70">{formatRelative(session.last_active_at)}</p>
        </div>
      </div>
    </button>
  );
}
