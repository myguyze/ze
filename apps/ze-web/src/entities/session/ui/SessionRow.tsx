import type { SessionSchema, SessionSearchResult } from "@myguyze/ze-client";
import { MessageSquare } from "lucide-react";
import { cn } from "@/shared/lib/cn";
import { matchSourceLabel } from "../lib/matchSourceLabel";
import { formatRelative } from "../lib/formatRelative";
import { parseSearchSnippet } from "../lib/parseSearchSnippet";
import { MarkdownPreview } from "./MarkdownPreview";

interface SessionRowProps {
  session: SessionSchema;
  active?: boolean;
  onSelect: () => void;
  searchSnippet?: string | null;
  matchSource?: SessionSearchResult["match_source"];
}

function SearchSnippet({ snippet }: { snippet: string }) {
  const parts = parseSearchSnippet(snippet);
  return (
    <p className="mt-1 text-xs leading-relaxed text-smoke line-clamp-2">
      {parts.map((part, index) =>
        part.highlight ? (
          <mark key={index} className="rounded bg-plum-voltage/20 px-0.5 text-white/90">
            {part.text}
          </mark>
        ) : (
          <span key={index}>{part.text}</span>
        ),
      )}
    </p>
  );
}

function SessionRowContent({
  session,
  searchSnippet,
}: {
  session: SessionSchema;
  searchSnippet?: string | null;
}) {
  const title = session.title;
  const preview = session.preview;

  if (searchSnippet) {
    return (
      <>
        <p className="text-sm font-medium text-white leading-snug line-clamp-1">
          {title ?? preview ?? "Untitled chat"}
        </p>
        <SearchSnippet snippet={searchSnippet} />
      </>
    );
  }

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

export function SessionRow({
  session,
  active = false,
  onSelect,
  searchSnippet,
  matchSource,
}: SessionRowProps) {
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
          <SessionRowContent session={session} searchSnippet={searchSnippet} />
          <div className="mt-1.5 flex items-center gap-2">
            <p className="text-[10px] text-smoke/80">{formatRelative(session.last_active_at)}</p>
            {matchSource && (
              <span className="rounded-full border border-white/10 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-smoke/80">
                {matchSourceLabel(matchSource)}
              </span>
            )}
          </div>
        </div>
      </div>
    </button>
  );
}
