import { Handle, Position, type NodeProps, type Node } from "@xyflow/react";
import { CheckCircle2, XCircle, Loader2, CircleSlash, Circle } from "lucide-react";
import { memo } from "react";
import type { StepState, WorkflowGraphNode } from "@/entities/workflow";
import { cn, motion } from "@/shared/lib";

export interface StepNodeData extends Record<string, unknown> {
  graphNode: WorkflowGraphNode;
  selected: boolean;
}

export type StepNodeType = Node<StepNodeData, "step">;

const STATE_ICON: Record<StepState, React.ComponentType<{ className?: string }>> = {
  "completed-ok": CheckCircle2,
  "completed-fail": XCircle,
  "failed-inferred": XCircle,
  running: Loader2,
  pending: Circle,
  "not-taken": CircleSlash,
};

const STATE_BORDER: Record<StepState, string> = {
  "completed-ok": "border-success/40",
  "completed-fail": "border-destructive/50",
  "failed-inferred": "border-destructive/30",
  running: "border-plum-voltage/60",
  pending: "border-white/10",
  "not-taken": "border-white/[0.06]",
};

const STATE_ICON_COLOR: Record<StepState, string> = {
  "completed-ok": "text-success",
  "completed-fail": "text-destructive",
  "failed-inferred": "text-destructive/50",
  running: "text-plum-voltage animate-spin",
  pending: "text-white/20",
  "not-taken": "text-white/20",
};

const STATE_TEXT_COLOR: Record<StepState, string> = {
  "completed-ok": "text-white",
  "completed-fail": "text-white",
  "failed-inferred": "text-white/50",
  running: "text-white",
  pending: "text-white/40",
  "not-taken": "text-white/25",
};

function StepNodeInner({ data }: NodeProps<StepNodeType>) {
  const { graphNode, selected } = data;
  const { step, state } = graphNode;
  const Icon = STATE_ICON[state];

  return (
    <div
      className={cn(
        "rounded-xl border bg-white/[0.03] px-3 py-2.5 w-[220px] cursor-pointer",
        motion.colors,
        STATE_BORDER[state],
        selected && "ring-1 ring-plum-voltage border-plum-voltage/60 bg-white/[0.06]",
      )}
    >
      <Handle type="target" position={Position.Top} className="!bg-white/20 !border-none !w-1.5 !h-1.5" />
      <div className="flex items-start gap-2">
        <Icon className={cn("w-4 h-4 flex-shrink-0 mt-0.5", STATE_ICON_COLOR[state])} />
        <p className={cn("text-xs leading-snug line-clamp-3", STATE_TEXT_COLOR[state])}>{step.task}</p>
      </div>
      {state === "not-taken" && <p className="mt-1 text-[10px] text-white/25 italic">Not taken this run</p>}
      <Handle type="source" position={Position.Bottom} className="!bg-white/20 !border-none !w-1.5 !h-1.5" />
    </div>
  );
}

export const StepNode = memo(StepNodeInner);
