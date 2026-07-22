import type { LoopListItem } from "@myguyze/ze-client";
import { ListTodo } from "lucide-react";
import { useLoopsQuery, useLoopTransitionMutation } from "@/entities/loop";
import { Button, ListPage } from "@/shared/ui";

const STATE_LABEL: Record<string, string> = {
  suspected: "Suspected",
  active: "Active",
  drifting: "Drifting",
  closed: "Closed",
  dropped: "Dropped",
};

function StateBadge({ state }: { state: string }) {
  const isSuspected = state === "suspected";
  return (
    <span
      className={
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium " +
        (isSuspected
          ? "bg-amber-500/15 text-amber-500"
          : "bg-emerald-500/15 text-emerald-500")
      }
    >
      {STATE_LABEL[state] ?? state}
    </span>
  );
}

function LoopRow({ loop }: { loop: LoopListItem }) {
  const transition = useLoopTransitionMutation();

  return (
    <div className="flex items-center justify-between gap-4 rounded-lg border border-white/10 px-4 py-3">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <StateBadge state={loop.state} />
          <span className="truncate text-sm font-medium">{loop.title}</span>
        </div>
        <p className="mt-1 text-xs text-smoke">
          {loop.provenance} · confidence {(loop.confidence * 100).toFixed(0)}%
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {loop.state === "suspected" && (
          <Button
            size="sm"
            variant="outline"
            disabled={transition.isPending}
            onClick={() => transition.mutate({ loopId: loop.id, kind: "confirm" })}
          >
            Confirm
          </Button>
        )}
        {(loop.state === "active" || loop.state === "drifting") && (
          <Button
            size="sm"
            variant="outline"
            disabled={transition.isPending}
            onClick={() => transition.mutate({ loopId: loop.id, kind: "close" })}
          >
            Close
          </Button>
        )}
        <Button
          size="sm"
          variant="ghost"
          disabled={transition.isPending}
          onClick={() => transition.mutate({ loopId: loop.id, kind: "drop" })}
        >
          Drop
        </Button>
      </div>
    </div>
  );
}

export function LoopReviewList() {
  const { data: loops, isLoading, isError, refetch } = useLoopsQuery();

  return (
    <ListPage
      isLoading={isLoading}
      isError={isError}
      isEmpty={!loops?.length}
      emptyIcon={ListTodo}
      emptyMessage="No open loops right now."
      errorMessage="Could not load open loops."
      onRetry={() => void refetch()}
    >
      <div className="space-y-2">
        {loops?.map((loop) => <LoopRow key={loop.id} loop={loop} />)}
      </div>
    </ListPage>
  );
}
