import { parsePrimitiveTree, type PrimitiveTree } from "@myguyze/ze-ui";
import { PrimitiveTreeRenderer } from "@myguyze/ze-ui/react";
import { FloatingButton } from "@/features/open-context-overlay";
import { usePluginScreenActions } from "@/entities/primitive-tree";
import type { UiContribution } from "@/entities/ui-manifest";
import { usePluginPageQuery } from "@/entities/ui-manifest";
import { useSetPageHeader } from "@/shared/lib";
import { EmptyState, ErrorState, ListSkeleton } from "@/shared/ui";
import { resolveNavIcon } from "@/shared/ui/icons";

export function PluginScreen({ entry }: { entry: UiContribution }) {
  const { data, isLoading, isError, refetch } = usePluginPageQuery(entry);
  const actions = usePluginScreenActions(() => {
    void refetch();
  });

  const Icon = resolveNavIcon(entry.icon);

  useSetPageHeader({ title: data?.title ?? entry.label, icon: Icon });

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

      <FloatingButton screen={entry.path ?? entry.id} />
    </div>
  );
}
