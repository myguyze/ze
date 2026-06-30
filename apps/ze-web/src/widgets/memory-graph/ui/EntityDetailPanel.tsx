import { X, User, MapPin, Building2, Hash, HelpCircle, ChevronDown } from "lucide-react";
import type { EntityDetailResponse, GraphEntityNode } from "@ze/client";

const ENTITY_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  person: User,
  place: MapPin,
  org: Building2,
  topic: Hash,
};

interface Props {
  entity: GraphEntityNode;
  detail: EntityDetailResponse | undefined;
  isLoading: boolean;
  onClose: () => void;
  onExpand: (neighbours: GraphEntityNode[], neighbourEdges: EntityDetailResponse["neighbour_edges"]) => void;
}

export function EntityDetailPanel({ entity, detail, isLoading, onClose, onExpand }: Props) {
  const Icon = ENTITY_ICONS[entity.entity_type] ?? HelpCircle;

  return (
    <div className="flex flex-col h-full bg-white/[0.03] border-l border-white/10 overflow-hidden">
      <div className="flex items-start justify-between p-4 border-b border-white/10 flex-shrink-0">
        <div className="flex items-center gap-2">
          <Icon className="w-4 h-4 text-smoke shrink-0" />
          <div>
            <p className="text-sm font-medium text-white leading-tight">{entity.canonical_name}</p>
            <p className="text-xs text-smoke">
              {entity.entity_type} &bull; {entity.degree} connections
            </p>
          </div>
        </div>
        <button onClick={onClose} className="text-smoke hover:text-white transition-colors shrink-0">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {isLoading && (
          <div className="text-xs text-smoke text-center py-4">Loading…</div>
        )}

        {detail && (
          <>
            {detail.facts.length > 0 && (
              <section>
                <p className="text-xs font-medium text-smoke uppercase tracking-wider mb-2">
                  Facts ({detail.facts.length})
                </p>
                <ul className="space-y-1">
                  {detail.facts.map((f) => (
                    <li key={String(f.id)} className="text-xs text-white/80">
                      <span className="text-smoke">{f.key}:</span>{" "}
                      {f.value}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {detail.episodes.length > 0 && (
              <section>
                <p className="text-xs font-medium text-smoke uppercase tracking-wider mb-2">
                  Episodes ({detail.episodes.length})
                </p>
                <ul className="space-y-1.5">
                  {detail.episodes.map((ep) => (
                    <li key={String(ep.id)} className="text-xs text-white/70 italic leading-snug">
                      "{ep.summary ?? "—"}"
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {detail.facts.length === 0 && detail.episodes.length === 0 && (
              <p className="text-xs text-smoke text-center py-4">
                No facts or episodes for this entity yet.
              </p>
            )}
          </>
        )}
      </div>

      {detail && detail.neighbours.length > 0 && (
        <div className="p-4 border-t border-white/10 flex-shrink-0">
          <button
            onClick={() => onExpand(detail.neighbours, detail.neighbour_edges)}
            className="w-full flex items-center justify-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-xs text-white/80 hover:bg-white/5 transition-colors"
          >
            <ChevronDown className="w-3 h-3" />
            Expand {detail.neighbours.length} neighbour{detail.neighbours.length !== 1 ? "s" : ""}
          </button>
        </div>
      )}
    </div>
  );
}
