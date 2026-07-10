import { useState } from "react";
import { Check, Loader2, Pencil, X } from "lucide-react";
import type { MemoryFeedItem } from "@myguyze/ze-client";
import { useReviewFactMutation } from "@/entities/memory-feed-item";
import type { MemoryFeedFilters } from "@/entities/memory-feed-item";
import { Input } from "@/shared/ui";

interface FactReviewActionsProps {
  item: MemoryFeedItem;
  filters: MemoryFeedFilters;
}

function IconButton({
  onClick,
  disabled,
  tone,
  label,
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  tone: "success" | "primary" | "danger" | "neutral";
  label: string;
  children: React.ReactNode;
}) {
  const toneClass =
    tone === "success"
      ? "text-success hover:bg-success/10 hover:border-success/30"
      : tone === "primary"
        ? "text-plum-voltage hover:bg-plum-voltage/10 hover:border-plum-voltage/30"
        : tone === "danger"
          ? "text-destructive hover:bg-destructive/10 hover:border-destructive/30"
          : "text-smoke hover:bg-white/5 hover:border-white/20";
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      className={`flex items-center justify-center size-6 rounded-full border border-transparent transition-colors disabled:opacity-40 ${toneClass}`}
    >
      {children}
    </button>
  );
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
      <div className="flex items-center gap-2 mt-2.5">
        <Input
          className="h-7 px-3 py-0 text-xs"
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submitEdit();
            if (e.key === "Escape") setEditing(false);
          }}
          autoFocus
        />
        <IconButton onClick={submitEdit} disabled={isPending} tone="success" label="Save">
          <Check className="size-3.5" />
        </IconButton>
        <IconButton onClick={() => setEditing(false)} tone="neutral" label="Cancel">
          <X className="size-3.5" />
        </IconButton>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1.5 mt-2.5">
      {isPending ? (
        <Loader2 className="size-3.5 text-smoke animate-spin" />
      ) : (
        <>
          <IconButton onClick={confirm} tone="success" label="Confirm this fact">
            <Check className="size-3.5" />
          </IconButton>
          <IconButton onClick={() => setEditing(true)} tone="primary" label="Edit this fact">
            <Pencil className="size-3.5" />
          </IconButton>
          <IconButton onClick={reject} tone="danger" label="Reject this fact">
            <X className="size-3.5" />
          </IconButton>
          <span className="text-[10px] text-smoke ml-1">Needs review</span>
        </>
      )}
    </div>
  );
}
