import { Bell } from "lucide-react";
import { FloatingButton } from "@/features/open-context-overlay";
import { ReminderRow, useRemindersQuery } from "@/entities/reminder";
import { PageHeader, EmptyState, ErrorState, ListSkeleton } from "@/shared/ui";

export function RemindersOverview() {
  const { data: reminders, isLoading, isError, refetch } = useRemindersQuery();

  const pending = reminders?.filter((r) => !r.fired) ?? [];
  const past = reminders?.filter((r) => r.fired) ?? [];

  return (
    <div className="px-4 py-8 space-y-6">
      <PageHeader label="Reminders" title="Upcoming" />

      {isLoading && <ListSkeleton count={2} height="h-14" />}

      {isError && (
        <ErrorState
          message="Could not load reminders."
          onRetry={() => void refetch()}
        />
      )}

      {!isError && !isLoading && pending.length === 0 && (
        <EmptyState icon={Bell} message="No reminders. Ask Ze to set one." />
      )}

      {!isError &&
        pending.map((reminder) => (
          <ReminderRow key={reminder.id} reminder={reminder} />
        ))}

      {!isError && past.length > 0 && (
        <div>
          <p className="text-xs text-smoke tracking-widest uppercase mb-3">Past</p>
          {past.slice(0, 5).map((reminder) => (
            <ReminderRow key={reminder.id} reminder={reminder} />
          ))}
        </div>
      )}

      <FloatingButton screen="reminders" />
    </div>
  );
}
