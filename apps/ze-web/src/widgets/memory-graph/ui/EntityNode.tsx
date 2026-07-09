import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { User, MapPin, Building2, Hash, HelpCircle } from "lucide-react";

export interface EntityNodeData {
  canonical_name: string;
  entity_type: string;
  degree: number;
  highlighted?: boolean;
  dimmed?: boolean;
}

// Categorical palette identifying entity type — distinct from the
// success/warning/destructive state tokens, so it intentionally doesn't use them.
const ENTITY_COLORS: Record<string, string> = {
  person: "bg-blue-500/20 border-blue-500/40 text-blue-300",
  place: "bg-green-500/20 border-green-500/40 text-green-300",
  org: "bg-amber-500/20 border-amber-500/40 text-amber-300",
  topic: "bg-purple-500/20 border-purple-500/40 text-purple-300",
};

const ENTITY_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  person: User,
  place: MapPin,
  org: Building2,
  topic: Hash,
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function EntityNodeInner({ data, selected }: NodeProps<any>) {
  const d = data as EntityNodeData;
  const colors = ENTITY_COLORS[d.entity_type] ?? "bg-white/10 border-white/20 text-smoke";
  const Icon = ENTITY_ICONS[d.entity_type] ?? HelpCircle;
  const size = Math.min(80, Math.max(40, 40 + d.degree * 3));
  const label = d.canonical_name.length > 20
    ? d.canonical_name.slice(0, 20) + "…"
    : d.canonical_name;

  return (
    <div
      style={{ width: size, height: size, opacity: d.dimmed ? 0.25 : 1 }}
      className={`
        relative flex flex-col items-center justify-center rounded-full border
        cursor-pointer transition-all duration-200 select-none
        ${colors}
        ${selected ? "ring-2 ring-white/60" : ""}
        ${d.highlighted ? "ring-2 ring-plum-voltage" : ""}
      `}
    >
      <Handle type="target" position={Position.Left} className="!w-1.5 !h-1.5 !border-0 !bg-white/30" />
      <Icon className="w-3 h-3 mb-0.5" />
      <span
        className="text-center leading-tight px-1"
        style={{ fontSize: Math.max(8, Math.min(10, size / 6)) }}
      >
        {label}
      </span>
      {d.degree > 0 && (
        <span
          className="absolute -top-1.5 -right-1.5 rounded-full bg-white/20 text-white px-1"
          style={{ fontSize: 7 }}
        >
          {d.degree}
        </span>
      )}
      <Handle type="source" position={Position.Right} className="!w-1.5 !h-1.5 !border-0 !bg-white/30" />
    </div>
  );
}

export const EntityNode = memo(EntityNodeInner);
