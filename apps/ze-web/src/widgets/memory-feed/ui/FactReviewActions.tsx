import { useState } from "react";
import type { MemoryFeedItem } from "@myguyze/ze-client";
import { useReviewFactMutation } from "@/entities/memory-feed-item";
import type { MemoryFeedFilters } from "@/entities/memory-feed-item";

interface FactReviewActionsProps {
  item: MemoryFeedItem;
  filters: MemoryFeedFilters;
}

export function FactReviewActions({ item, filters }: FactReviewActionsProps) {
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState(item.value ?? "");
  const { mutate, isPending } = useReviewFactMutation(filters);

  function confirm() {
    mutate({ actions: [{ id: item.id, action: "confirm" }] });
  }

  function reject() {
    mutate({ actions: [{ id: item.id, action: "reject" }] });
  }

  function submitEdit() {
    mutate({ actions: [{ id: item.id, action: "edit", value: editValue }] });
    setEditing(false);
  }

  if (editing) {
    return (
      <div className="flex items-center gap-2 mt-1">
        <input
          className="flex-1 bg-white/5 border border-white/10 rounded px-2 py-0.5 text-xs text-white"
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submitEdit();
            if (e.key === "Escape") setEditing(false);
          }}
          autoFocus
        />
        <button
          onClick={submitEdit}
          className="text-xs text-green-400 hover:text-green-300"
          disabled={isPending}
        >
          Save
        </button>
        <button
          onClick={() => setEditing(false)}
          className="text-xs text-smoke hover:text-white"
        >
          Cancel
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3 mt-1">
      <button
        onClick={confirm}
        className="text-xs text-green-400 hover:text-green-300"
        disabled={isPending}
      >
        Confirm
      </button>
      <button
        onClick={() => setEditing(true)}
        className="text-xs text-blue-400 hover:text-blue-300"
        disabled={isPending}
      >
        Edit
      </button>
      <button
        onClick={reject}
        className="text-xs text-red-400 hover:text-red-300"
        disabled={isPending}
      >
        Reject
      </button>
    </div>
  );
}
