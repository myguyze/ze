import { useCallback, useEffect, useRef, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  type Edge,
  type Node,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
} from "@xyflow/react";
import { layout as dagreLayout, graphlib } from "@dagrejs/dagre";
import "@xyflow/react/dist/style.css";
import type { EntityDetailResponse, GraphEdge, GraphEntityNode, MemoryGraphResponse } from "@ze/client";
import { EntityNode } from "./EntityNode";
import { EntityDetailPanel } from "./EntityDetailPanel";
import { GraphSearchBar } from "./GraphSearchBar";
import { GraphToolbar } from "./GraphToolbar";
import { useEntityDetailQuery } from "@/entities/memory-graph";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const NODE_TYPES: Record<string, any> = { entity: EntityNode };

function toFlowNode(entity: GraphEntityNode, search: string): Node {
  const name = entity.canonical_name.toLowerCase();
  const aliases = (entity.aliases as string[]).map((a) => a.toLowerCase());
  const matched = search
    ? name.includes(search.toLowerCase()) || aliases.some((a) => a.includes(search.toLowerCase()))
    : true;
  return {
    id: String(entity.id),
    type: "entity",
    position: { x: 0, y: 0 },
    data: {
      canonical_name: entity.canonical_name,
      entity_type: entity.entity_type,
      degree: entity.degree,
      highlighted: search ? matched : false,
      dimmed: search ? !matched : false,
    },
  };
}

function toFlowEdge(edge: GraphEdge): Edge {
  return {
    id: String(edge.id),
    source: String(edge.source_id),
    target: String(edge.target_id),
    label: edge.predicate,
    style: {
      stroke: edge.confidence < 0.5 ? "rgba(255,255,255,0.15)" : "rgba(255,255,255,0.25)",
      strokeDasharray: edge.confidence < 0.5 ? "4 3" : undefined,
    },
    labelStyle: { fill: "rgba(255,255,255,0.4)", fontSize: 9 },
    labelShowBg: false,
  };
}

function applyDagreLayout(nodes: Node[], edges: Edge[]): Node[] {
  const g = new graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 60, ranksep: 80 });

  nodes.forEach((n) => {
    const degree = (n.data?.degree as number) ?? 0;
    const size = Math.min(80, Math.max(40, 40 + degree * 3));
    g.setNode(n.id, { width: size, height: size });
  });
  edges.forEach((e) => g.setEdge(e.source, e.target));

  dagreLayout(g);

  return nodes.map((n) => {
    const pos = g.node(n.id);
    if (!pos) return n;
    return { ...n, position: { x: pos.x - pos.width / 2, y: pos.y - pos.height / 2 } };
  });
}

interface GraphCanvasProps {
  data: MemoryGraphResponse;
  entityType: string;
  onEntityTypeChange: (t: string) => void;
}

function GraphCanvas({ data, entityType, onEntityTypeChange }: GraphCanvasProps) {
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const { fitView } = useReactFlow();
  const initialized = useRef(false);

  const rebuildGraph = useCallback(
    (graphData: MemoryGraphResponse, searchTerm: string) => {
      const flowNodes = graphData.nodes.map((e) => toFlowNode(e, searchTerm));
      const flowEdges = graphData.edges.map(toFlowEdge);
      const laid = applyDagreLayout(flowNodes, flowEdges);
      setNodes(laid);
      setEdges(flowEdges);
      setTimeout(() => fitView({ padding: 0.15 }), 50);
    },
    [setNodes, setEdges, fitView],
  );

  useEffect(() => {
    if (!initialized.current) {
      initialized.current = true;
      rebuildGraph(data, search);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  const applySearch = useCallback(
    (term: string) => {
      setSearch(term);
      setNodes((nds) =>
        nds.map((n) => {
          const name = String(n.data?.canonical_name ?? "").toLowerCase();
          const matched = term ? name.includes(term.toLowerCase()) : true;
          return {
            ...n,
            data: { ...n.data, highlighted: term ? matched : false, dimmed: term ? !matched : false },
          };
        }),
      );
    },
    [setNodes],
  );

  const { data: detail, isLoading: detailLoading } = useEntityDetailQuery(selectedId);

  const handleExpand = useCallback(
    (neighbours: GraphEntityNode[], neighbourEdges: EntityDetailResponse["neighbour_edges"]) => {
      setNodes((nds) => {
        const existingIds = new Set(nds.map((n) => n.id));
        const newNodes = neighbours
          .filter((nb) => !existingIds.has(String(nb.id)))
          .map((nb) => toFlowNode(nb, search));
        if (newNodes.length === 0) return nds;
        const combined = [...nds, ...newNodes];
        return applyDagreLayout(combined, edges);
      });
      setEdges((eds) => {
        const existingEdgeIds = new Set(eds.map((e) => e.id));
        const newEdges = (neighbourEdges as GraphEdge[])
          .filter((e) => !existingEdgeIds.has(String(e.id)))
          .map(toFlowEdge);
        return [...eds, ...newEdges];
      });
      setTimeout(() => fitView({ padding: 0.15 }), 100);
    },
    [edges, search, setEdges, setNodes, fitView],
  );

  const selectedEntity = selectedId
    ? (data.nodes.find((n) => String(n.id) === selectedId) ?? null)
    : null;

  return (
    <div className="flex h-full">
      <div className="flex-1 relative">
        <div className="absolute top-3 left-3 z-10 flex items-center gap-2 flex-wrap">
          <GraphToolbar
            entityType={entityType as "all"}
            onEntityTypeChange={onEntityTypeChange}
            onResetLayout={() => rebuildGraph(data, search)}
          />
          <GraphSearchBar value={search} onChange={applySearch} />
        </div>

        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={(_, node) => setSelectedId((prev) => (prev === node.id ? null : node.id))}
          fitView
          className="bg-transparent"
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="rgba(255,255,255,0.05)" />
          <Controls className="!bg-white/5 !border-white/10 !shadow-none" />
        </ReactFlow>

        {nodes.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <p className="text-sm text-smoke">No entities found.</p>
          </div>
        )}
      </div>

      {selectedEntity && (
        <div className="w-72 shrink-0 overflow-hidden">
          <EntityDetailPanel
            entity={selectedEntity}
            detail={detail}
            isLoading={detailLoading}
            onClose={() => setSelectedId(null)}
            onExpand={handleExpand}
          />
        </div>
      )}
    </div>
  );
}

interface MemoryGraphProps {
  data: MemoryGraphResponse;
  entityType: string;
  onEntityTypeChange: (t: string) => void;
}

export function MemoryGraph({ data, entityType, onEntityTypeChange }: MemoryGraphProps) {
  return (
    <ReactFlowProvider>
      <GraphCanvas data={data} entityType={entityType} onEntityTypeChange={onEntityTypeChange} />
    </ReactFlowProvider>
  );
}
