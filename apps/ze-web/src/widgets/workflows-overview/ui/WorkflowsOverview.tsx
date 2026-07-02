import { useMemo, useState } from "react";
import { Workflow } from "lucide-react";
import { FloatingButton } from "@/features/open-context-overlay";
import { useWorkflowsQuery, WorkflowCard } from "@/entities/workflow";
import { ListPage, SearchBar, FilterChips, ViewToggle, SortSelect } from "@/shared/ui";
import type { FilterOption, ViewMode, SortOption } from "@/shared/ui";

type StatusFilter = "all" | "active" | "paused";
type SortKey = "next_run" | "last_run" | "name" | "created";

const STATUS_FILTERS: FilterOption<StatusFilter>[] = [
  { label: "All", value: "all" },
  { label: "Active", value: "active" },
  { label: "Paused", value: "paused" },
];

const SORT_OPTIONS: SortOption<SortKey>[] = [
  { label: "Next run", value: "next_run" },
  { label: "Last run", value: "last_run" },
  { label: "Name A→Z", value: "name" },
  { label: "Created", value: "created" },
];

export function WorkflowsOverview() {
  const { data: workflows, isLoading, isError, refetch } = useWorkflowsQuery();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [sort, setSort] = useState<SortKey>("next_run");
  const [view, setView] = useState<ViewMode>("list");

  const filtered = useMemo(() => {
    if (!workflows) return [];

    let result = workflows.filter((w) => {
      if (status === "active" && !w.enabled) return false;
      if (status === "paused" && w.enabled) return false;
      if (search) {
        const q = search.toLowerCase();
        return w.name.toLowerCase().includes(q) || w.description?.toLowerCase().includes(q);
      }
      return true;
    });

    result = [...result].sort((a, b) => {
      switch (sort) {
        case "next_run": {
          if (!a.next_run_at && !b.next_run_at) return 0;
          if (!a.next_run_at) return 1;
          if (!b.next_run_at) return -1;
          return new Date(a.next_run_at).getTime() - new Date(b.next_run_at).getTime();
        }
        case "last_run": {
          if (!a.last_run_at && !b.last_run_at) return 0;
          if (!a.last_run_at) return 1;
          if (!b.last_run_at) return -1;
          return new Date(b.last_run_at).getTime() - new Date(a.last_run_at).getTime();
        }
        case "name":
          return a.name.localeCompare(b.name);
        case "created":
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      }
    });

    return result;
  }, [workflows, search, status, sort]);

  const isFilteredEmpty = !isLoading && !isError && !!workflows?.length && filtered.length === 0;

  const toolbar = (
    <div className="flex items-center gap-3 flex-wrap">
      <SearchBar
        value={search}
        onChange={setSearch}
        placeholder="Search workflows…"
        className="w-48 shrink-0"
      />
      <FilterChips options={STATUS_FILTERS} value={status} onChange={setStatus} />
      <div className="ml-auto flex items-center gap-2 shrink-0">
        <SortSelect options={SORT_OPTIONS} value={sort} onChange={setSort} />
        <ViewToggle value={view} onChange={setView} />
      </div>
    </div>
  );

  return (
    <>
      <ListPage
        isLoading={isLoading}
        isError={isError}
        isEmpty={!workflows?.length}
        emptyIcon={Workflow}
        emptyMessage="No workflows yet. Ask Ze to create one."
        errorMessage="Could not load workflows."
        onRetry={() => void refetch()}
        toolbar={toolbar}
      >
        {isFilteredEmpty ? (
          <p className="text-sm text-smoke text-center py-12">No workflows match your filters.</p>
        ) : view === "grid" ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {filtered.map((workflow) => (
              <WorkflowCard key={workflow.id} workflow={workflow} variant="grid" />
            ))}
          </div>
        ) : (
          <div className="space-y-2">
            {filtered.map((workflow) => (
              <WorkflowCard key={workflow.id} workflow={workflow} variant="row" />
            ))}
          </div>
        )}
      </ListPage>

      <FloatingButton screen="workflows" />
    </>
  );
}
