import type { ReminderListItem } from "@ze/client";

export function ReminderRow({ reminder }: { reminder: ReminderListItem }) {
  if (reminder.fired) {
    return (
      <div className="flex items-center justify-between p-4 rounded-pill opacity-40">
        <p className="text-sm text-white line-through">{reminder.label}</p>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-between p-4 rounded-pill border border-white/10">
      <p className="text-sm text-white">{reminder.label}</p>
      <p className="text-xs text-smoke">
        {new Date(reminder.fire_at).toLocaleString([], { dateStyle: "short", timeStyle: "short" })}
      </p>
    </div>
  );
}
