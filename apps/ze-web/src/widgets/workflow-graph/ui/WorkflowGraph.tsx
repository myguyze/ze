import type { WorkflowStepResponse, WorkflowExecutionResponse } from "@myguyze/ze-client";
import { ReactFlow, ReactFlowProvider, Background, useReactFlow, type Node, type Edge } from "@xyflow/react";
import { useEffect, useMemo, useRef, useState } from "react";
import "@xyflow/react/dist/style.css";
import { buildWorkflowGraph } from "@/entities/workflow";
import { layoutGraph } from "../lib/layout";
import { StepDetailPanel } from "./StepDetailPanel";
import { StepNode, type StepNodeData } from "./StepNode";
import { WorkflowGraphToolbar } from "./WorkflowGraphToolbar";

const nodeTypes = { step: StepNode };

interface Props {
  steps: WorkflowStepResponse[];
  execution?: WorkflowExecutionResponse | null;
  isLive?: boolean;
}

function WorkflowGraphInner({ steps, execution }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hideNotTaken, setHideNotTaken] = useState(false);
  const { fitView } = useReactFlow();
  const hasFitted = useRef(false);

  const graph = useMemo(() => buildWorkflowGraph(steps, execution ?? null), [steps, execution]);

  useEffect(() => {
    // Re-fit whenever we switch to a different execution (different run selected).
    hasFitted.current = false;
  }, [execution?.id]);

  const { nodes, edges } = useMemo(() => {
    const visibleNodes = hideNotTaken ? graph.nodes.filter((n) => n.state !== "not-taken") : graph.nodes;
    const visibleIds = new Set(visibleNodes.map((n) => n.id));

    const rfNodes: Node<StepNodeData>[] = visibleNodes.map((graphNode) => ({
      id: graphNode.id,
      type: "step",
      position: { x: 0, y: 0 },
      data: { graphNode, selected: graphNode.id === selectedId },
      draggable: false,
    }));

    const rfEdges: Edge[] = graph.edges
      .filter((e) => visibleIds.has(e.from) && visibleIds.has(e.to))
      .map((e) => ({
        id: e.id,
        source: e.from,
        target: e.to,
        label: e.label ?? undefined,
        animated: e.taken && execution?.status === "running",
        style: {
          stroke: e.taken ? "var(--color-plum-voltage)" : "rgba(255,255,255,0.12)",
          strokeWidth: e.taken ? 2 : 1,
        },
        labelStyle: { fill: e.taken ? "#fff" : "rgba(255,255,255,0.4)", fontSize: 11 },
        labelBgStyle: { fill: "#000" },
      }));

    return { nodes: layoutGraph(rfNodes, rfEdges), edges: rfEdges };
  }, [graph, hideNotTaken, selectedId, execution?.status]);

  useEffect(() => {
    if (hasFitted.current || nodes.length === 0) return;
    hasFitted.current = true;
    const raf = requestAnimationFrame(() => fitView({ padding: 0.2, duration: 0 }));
    return () => cancelAnimationFrame(raf);
  }, [nodes, fitView]);

  const selectedNode = selectedId ? (graph.nodes.find((n) => n.id === selectedId) ?? null) : null;

  if (!steps.length) {
    return <p className="text-sm text-smoke">No steps defined.</p>;
  }

  return (
    <div className="flex h-full min-h-[480px]">
      <div className="flex-1 relative rounded-xl border border-white/[0.06] overflow-hidden bg-white/[0.01]">
        <div className="absolute top-3 left-3 z-10">
          <WorkflowGraphToolbar
            hideNotTaken={hideNotTaken}
            onToggleHideNotTaken={() => setHideNotTaken((v) => !v)}
            onFitView={() => fitView({ padding: 0.2, duration: 300 })}
          />
        </div>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodeClick={(_, node) => setSelectedId((prev) => (prev === node.id ? null : node.id))}
          onPaneClick={() => setSelectedId(null)}
          nodesDraggable={false}
          nodesConnectable={false}
          minZoom={0.2}
          maxZoom={1.5}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="rgba(255,255,255,0.05)" gap={24} />
        </ReactFlow>
      </div>

      {selectedNode && (
        <div className="w-72 shrink-0 overflow-hidden ml-3">
          <StepDetailPanel
            node={selectedNode}
            executionError={execution?.error ?? null}
            onClose={() => setSelectedId(null)}
          />
        </div>
      )}
    </div>
  );
}

export function WorkflowGraph(props: Props) {
  return (
    <ReactFlowProvider>
      <WorkflowGraphInner {...props} />
    </ReactFlowProvider>
  );
}
