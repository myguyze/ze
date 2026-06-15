import { useQuery } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { api } from "@/lib/api";
import { type Reminder } from "@/types/api";
import { FloatingButton } from "@/features/overlay/FloatingButton";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/layout/EmptyState";
import { ListSkeleton } from "@/components/layout/ListSkeleton";

export function RemindersPage() {
  const { data: reminders, isLoading } = useQuery({
    queryKey: ["reminders"],
    queryFn: () => api.get<Reminder[]>("/api/reminders"),
  });

  const pending = reminders?.filter((r) => !r.fired) ?? [];
  const past = reminders?.filter((r) => r.fired) ?? [];

  return (
    <div className="px-4 py-8 space-y-6">
      <PageHeader label="Reminders" title="Upcoming" />

      {isLoading && <ListSkeleton count={2} height="h-14" />}

      {!isLoading && pending.length === 0 && (
        <EmptyState icon={Bell} message="No reminders. Ask Ze to set one." />
      )}

      {pending.map((r) => (
        <div key={r.id} className="flex items-center justify-between p-4 rounded-[24px] border border-white/10">
          <p className="text-sm text-white">{r.label}</p>
          <p className="text-xs text-[#9a9a9a]">
            {new Date(r.fire_at).toLocaleString([], { dateStyle: "short", timeStyle: "short" })}
          </p>
        </div>
      ))}

      {past.length > 0 && (
        <div>
          <p className="text-xs text-[#9a9a9a] tracking-widest uppercase mb-3">Past</p>
          {past.slice(0, 5).map((r) => (
            <div key={r.id} className="flex items-center justify-between p-4 rounded-[24px] opacity-40">
              <p className="text-sm text-white line-through">{r.label}</p>
            </div>
          ))}
        </div>
      )}

      <FloatingButton screen="reminders" />
    </div>
  );
}
