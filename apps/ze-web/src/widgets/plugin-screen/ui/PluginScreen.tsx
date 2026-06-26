import { parsePrimitiveTree, type PrimitiveTree } from "@ze/ui";
import { PrimitiveTreeRenderer } from "@ze/ui/react";
import { FloatingButton } from "@/features/open-context-overlay";
import type { UiContribution } from "@/entities/ui-manifest";
import { usePluginPageQuery } from "@/entities/ui-manifest";
import { resolveNavIcon } from "@/shared/ui/icons";
import { EmptyState, ErrorState, ListSkeleton } from "@/shared/ui";
import { usePluginScreenActions } from "../api/usePluginScreenActions";

export function PluginScreen({ entry }: { entry: UiContribution }) {
  const path = entry.path ?? "";
  const { data, isLoading, isError, refetch } = usePluginPageQuery(path);
  const actions = usePluginScreenActions(() => {
    void refetch();
  });

  const Icon = resolveNavIcon(entry.icon);

  let nodes: PrimitiveTree | null = null;
  if (data?.tree) {
    try {
      nodes = parsePrimitiveTree(data.tree);
    } catch {
      nodes = null;
    }
  }

  return (
    <div className="px-4 py-6 max-w-2xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <Icon className="w-5 h-5 text-plum-voltage" />
        <h1 className="text-lg font-semibold text-white">{data?.title ?? entry.label}</h1>
      </div>

      {isLoading && <ListSkeleton count={6} />}

      {isError && (
        <ErrorState
          message={`Could not load ${entry.label.toLowerCase()}.`}
          onRetry={() => void refetch()}
        />
      )}

      {!isLoading && !isError && nodes && nodes.length === 0 && (
        <EmptyState icon={Icon} message="Nothing to show yet." />
      )}

      {!isLoading && !isError && nodes && nodes.length > 0 && (
        <PrimitiveTreeRenderer nodes={nodes} actions={actions} />
      )}

      {!isLoading && !isError && data && !nodes && (
        <ErrorState message="This page returned an invalid UI tree." onRetry={() => void refetch()} />
      )}

      <FloatingButton screen={path} />
    </div>
  );
}
