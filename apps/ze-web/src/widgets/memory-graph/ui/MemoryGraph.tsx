import type { EntityDetailResponse, GraphEdge, GraphEntityNode, MemoryGraphResponse } from "@myguyze/ze-client";
import { useCallback, useMemo, useRef, useState } from "react";
import ForceGraph3D, { type ForceGraphMethods } from "react-force-graph-3d";
import { useEntityDetailQuery } from "@/entities/memory-graph";
import { EntityDetailPanel } from "./EntityDetailPanel";
import { buildEntityNodeObject, entityColor, entityRadius, type GraphNodeDatum } from "./entityNodeObject";
import { GraphSearchBar } from "./GraphSearchBar";
import { GraphToolbar } from "./GraphToolbar";

interface GraphLinkDatum {
  id: string;
  source: string;
  target: string;
  predicate: string;
  confidence: number;
}

function matchesSearch(entity: Pick<GraphEntityNode, "canonical_name" | "aliases">, search: string): boolean {
  if (!search) return true;
  const term = search.toLowerCase();
  const name = entity.canonical_name.toLowerCase();
  const aliases = (entity.aliases as string[]).map((a) => a.toLowerCase());
  return name.includes(term) || aliases.some((a) => a.includes(term));
}

function toGraphNode(entity: GraphEntityNode, search: string): GraphNodeDatum {
  const matched = matchesSearch(entity, search);
  return {
    id: String(entity.id),
    canonical_name: entity.canonical_name,
    entity_type: entity.entity_type,
    degree: entity.degree,
    highlighted: search ? matched : false,
    dimmed: search ? !matched : false,
  };
}

function toGraphLink(edge: GraphEdge): GraphLinkDatum {
  return {
    id: String(edge.id),
    source: String(edge.source_id),
    target: String(edge.target_id),
    predicate: edge.predicate,
    confidence: edge.confidence,
  };
}

interface MemoryGraphProps {
  data: MemoryGraphResponse;
  entityType: string;
  onEntityTypeChange: (t: string) => void;
}

export function MemoryGraph({ data, entityType, onEntityTypeChange }: MemoryGraphProps) {
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [extraNodes, setExtraNodes] = useState<GraphEntityNode[]>([]);
  const [extraEdges, setExtraEdges] = useState<GraphEdge[]>([]);
  const fgRef = useRef<ForceGraphMethods<GraphNodeDatum, GraphLinkDatum> | undefined>(undefined);
  const containerRef = useRef<HTMLDivElement>(null);
  const hasFitted = useRef(false);

  const allEntities = useMemo(() => {
    const existingIds = new Set(data.nodes.map((n) => n.id));
    return [...data.nodes, ...extraNodes.filter((n) => !existingIds.has(n.id))];
  }, [data.nodes, extraNodes]);

  const allEdges = useMemo(() => {
    const existingIds = new Set(data.edges.map((e) => e.id));
    return [...data.edges, ...extraEdges.filter((e) => !existingIds.has(e.id))];
  }, [data.edges, extraEdges]);

  const graphData = useMemo(
    () => ({
      nodes: allEntities.map((e) => toGraphNode(e, search)),
      links: allEdges.map(toGraphLink),
    }),
    [allEntities, allEdges, search],
  );

  const { data: detail, isLoading: detailLoading } = useEntityDetailQuery(selectedId);

  const handleExpand = useCallback(
    (neighbours: GraphEntityNode[], neighbourEdges: EntityDetailResponse["neighbour_edges"]) => {
      setExtraNodes((prev) => {
        const existingIds = new Set([...allEntities.map((n) => n.id)]);
        const additions = neighbours.filter((n) => !existingIds.has(n.id));
        return additions.length ? [...prev, ...additions] : prev;
      });
      setExtraEdges((prev) => {
        const existingIds = new Set(allEdges.map((e) => e.id));
        const additions = (neighbourEdges as GraphEdge[]).filter((e) => !existingIds.has(e.id));
        return additions.length ? [...prev, ...additions] : prev;
      });
      setTimeout(() => fgRef.current?.zoomToFit(600, 80), 150);
    },
    [allEntities, allEdges],
  );

  const resetLayout = useCallback(() => {
    fgRef.current?.d3ReheatSimulation();
    setTimeout(() => fgRef.current?.zoomToFit(600, 80), 100);
  }, []);

  const fitView = useCallback(() => {
    fgRef.current?.zoomToFit(600, 80);
  }, []);

  const handleEngineStop = useCallback(() => {
    if (hasFitted.current) return;
    hasFitted.current = true;
    fgRef.current?.zoomToFit(600, 80);
  }, []);

  const selectedEntity = selectedId ? (allEntities.find((n) => String(n.id) === selectedId) ?? null) : null;

  return (
    <div className="flex h-full">
      <div className="flex-1 relative" ref={containerRef}>
        <div className="absolute top-3 left-3 z-10 flex items-center gap-2 flex-wrap">
          <GraphToolbar
            entityType={entityType as "all"}
            onEntityTypeChange={onEntityTypeChange}
            onFitView={fitView}
            onResetLayout={resetLayout}
          />
          <GraphSearchBar value={search} onChange={setSearch} />
        </div>

        <ForceGraph3D
          ref={fgRef}
          graphData={graphData}
          backgroundColor="rgba(0,0,0,0)"
          showNavInfo={false}
          nodeLabel={(n) => n.canonical_name}
          nodeVal={(n) => entityRadius(n.degree)}
          nodeThreeObject={buildEntityNodeObject}
          nodeThreeObjectExtend={false}
          linkColor={(l) => (l.confidence < 0.5 ? "rgba(255,255,255,0.12)" : "rgba(255,255,255,0.22)")}
          linkLabel={(l) => l.predicate}
          linkWidth={1}
          linkOpacity={0.6}
          onNodeClick={(n) => setSelectedId((prev) => (prev === n.id ? null : (n.id as string)))}
          onBackgroundClick={() => setSelectedId(null)}
          onEngineStop={handleEngineStop}
        />

        {graphData.nodes.length === 0 && (
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

export { entityColor };
