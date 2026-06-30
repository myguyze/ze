import { useState } from "react";
import { Network } from "lucide-react";
import { useMemoryGraphQuery } from "@/entities/memory-graph";
import { MemoryGraph } from "@/widgets/memory-graph";
import { PageHeader, EmptyState, ErrorState } from "@/shared/ui";

export function BrainGraphPage() {
  const [entityType, setEntityType] = useState("all");

  const { data, isPending, isError } = useMemoryGraphQuery({
    entityType: entityType === "all" ? undefined : entityType,
    limit: 50,
  });

  return (
    <div className="flex flex-col h-full px-4 py-6 gap-4">
      <PageHeader label="Brain" title="Memory Graph" />

      {isPending && (
        <div className="flex-1 flex items-center justify-center text-sm text-smoke">
          Loading graph…
        </div>
      )}

      {isError && (
        <ErrorState message="Could not load the memory graph." />
      )}

      {data && data.nodes.length === 0 && (
        <EmptyState
          icon={Network}
          message="No entities in memory yet."
          detail="Start chatting with Ze to build up a memory graph."
        />
      )}

      {data && data.nodes.length > 0 && (
        <div className="flex-1 rounded-xl border border-white/10 overflow-hidden">
          <MemoryGraph
            data={data}
            entityType={entityType}
            onEntityTypeChange={setEntityType}
          />
        </div>
      )}
    </div>
  );
}
