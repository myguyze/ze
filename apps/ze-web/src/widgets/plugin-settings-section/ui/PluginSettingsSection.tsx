import { ChevronDown } from "lucide-react";
import { useState } from "react";
import { parsePrimitiveTree, type PrimitiveTree } from "@ze/ui";
import { PrimitiveTreeRenderer } from "@ze/ui/react";
import type { UiContribution } from "@/entities/ui-manifest";
import { usePluginSettingsQuery } from "@/entities/ui-manifest";
import { resolveNavIcon } from "@/shared/ui/icons";
import { cn } from "@/shared/lib/cn";
import { ErrorState, ListSkeleton } from "@/shared/ui";
import { usePluginScreenActions } from "@/entities/primitive-tree";

export function PluginSettingsSection({ entry }: { entry: UiContribution }) {
  const [open, setOpen] = useState(true);
  const { data, isLoading, isError, refetch } = usePluginSettingsQuery(entry, open);
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
    <div className="space-y-3 pt-4 border-t border-white/10">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="w-full flex items-center justify-between gap-3 text-left"
      >
        <span className="flex items-center gap-2 text-xs font-semibold tracking-widest uppercase text-smoke">
          <Icon className="w-3.5 h-3.5" />
          {entry.label}
        </span>
        <ChevronDown className={cn("w-4 h-4 text-smoke transition-transform", open && "rotate-180")} />
      </button>

      {open && isLoading && <ListSkeleton count={3} />}

      {open && isError && (
        <ErrorState
          message={`Could not load ${entry.label.toLowerCase()} settings.`}
          onRetry={() => void refetch()}
        />
      )}

      {open && !isLoading && !isError && nodes && nodes.length > 0 && (
        <PrimitiveTreeRenderer nodes={nodes} actions={actions} />
      )}

      {open && !isLoading && !isError && data && !nodes && (
        <ErrorState message="Invalid settings UI tree." onRetry={() => void refetch()} />
      )}
    </div>
  );
}
