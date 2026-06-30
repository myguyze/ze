import { ZoomIn, ZoomOut, Maximize2, RotateCcw } from "lucide-react";
import { useReactFlow } from "@xyflow/react";

const ENTITY_TYPES = ["all", "person", "place", "org", "topic"] as const;
type EntityTypeFilter = (typeof ENTITY_TYPES)[number];

interface Props {
  entityType: EntityTypeFilter;
  onEntityTypeChange: (type: EntityTypeFilter) => void;
  onResetLayout: () => void;
}

export function GraphToolbar({ entityType, onEntityTypeChange, onResetLayout }: Props) {
  const { zoomIn, zoomOut, fitView } = useReactFlow();

  return (
    <div className="flex items-center gap-2">
      <div className="flex items-center gap-1 rounded-lg border border-white/10 p-1">
        {ENTITY_TYPES.map((t) => (
          <button
            key={t}
            onClick={() => onEntityTypeChange(t)}
            className={`px-2 py-1 rounded text-xs capitalize transition-colors ${
              entityType === t
                ? "bg-plum-voltage/20 text-white"
                : "text-smoke hover:text-white"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-1 rounded-lg border border-white/10 p-1">
        <button
          onClick={() => zoomIn()}
          className="p-1 rounded text-smoke hover:text-white transition-colors"
          title="Zoom in"
        >
          <ZoomIn className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={() => zoomOut()}
          className="p-1 rounded text-smoke hover:text-white transition-colors"
          title="Zoom out"
        >
          <ZoomOut className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={() => fitView({ padding: 0.2 })}
          className="p-1 rounded text-smoke hover:text-white transition-colors"
          title="Fit view"
        >
          <Maximize2 className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={onResetLayout}
          className="p-1 rounded text-smoke hover:text-white transition-colors"
          title="Reset layout"
        >
          <RotateCcw className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
