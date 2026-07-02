import { useMemo, useState } from "react";
import { Target } from "lucide-react";
import { FloatingButton } from "@/features/open-context-overlay";
import { GoalCard, useGoalsQuery } from "@/entities/goal";
import { ListPage, SearchBar, FilterChips, ViewToggle, SortSelect } from "@/shared/ui";
import type { FilterOption, ViewMode, SortOption } from "@/shared/ui";

type StatusFilter = "all" | "planning" | "active" | "completed" | "abandoned";
type SortKey = "created" | "name" | "status";

const STATUS_FILTERS: FilterOption<StatusFilter>[] = [
  { label: "All", value: "all" },
  { label: "Active", value: "active" },
  { label: "Planning", value: "planning" },
  { label: "Completed", value: "completed" },
  { label: "Abandoned", value: "abandoned" },
];

const SORT_OPTIONS: SortOption<SortKey>[] = [
  { label: "Created", value: "created" },
  { label: "Name A→Z", value: "name" },
  { label: "Status", value: "status" },
];

export function GoalsOverview() {
  const { data: goals, isLoading, isError, refetch } = useGoalsQuery();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [sort, setSort] = useState<SortKey>("created");
  const [view, setView] = useState<ViewMode>("list");

  const filtered = useMemo(() => {
    if (!goals) return [];

    let result = goals.filter((g) => {
      if (status !== "all" && g.status !== status) return false;
      if (search) {
        const q = search.toLowerCase();
        return g.title.toLowerCase().includes(q) || g.objective.toLowerCase().includes(q);
      }
      return true;
    });

    result = [...result].sort((a, b) => {
      switch (sort) {
        case "name":
          return a.title.localeCompare(b.title);
        case "status":
          return a.status.localeCompare(b.status);
        case "created":
        default:
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      }
    });

    return result;
  }, [goals, search, status, sort]);

  const isFilteredEmpty = !isLoading && !isError && !!goals?.length && filtered.length === 0;

  const toolbar = (
    <div className="flex items-center gap-3 flex-wrap">
      <SearchBar
        value={search}
        onChange={setSearch}
        placeholder="Search goals…"
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
        isEmpty={!goals?.length}
        emptyIcon={Target}
        emptyMessage="No goals yet. Ask Ze to set one."
        errorMessage="Could not load goals."
        onRetry={() => void refetch()}
        toolbar={toolbar}
      >
        {isFilteredEmpty ? (
          <p className="text-sm text-smoke text-center py-12">No goals match your filters.</p>
        ) : view === "grid" ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {filtered.map((goal) => (
              <GoalCard key={goal.id} goal={goal} variant="grid" />
            ))}
          </div>
        ) : (
          <div className="space-y-2">
            {filtered.map((goal) => (
              <GoalCard key={goal.id} goal={goal} variant="row" />
            ))}
          </div>
        )}
      </ListPage>

      <FloatingButton screen="goals" />
    </>
  );
}
