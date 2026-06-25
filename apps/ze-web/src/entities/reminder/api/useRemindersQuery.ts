import { useQuery } from "@tanstack/react-query";
import { listReminders } from "@ze/client";
import type { ReminderListItem } from "@ze/client";
import { queryKeys } from "@/shared/lib";

export function useRemindersQuery() {
  return useQuery<ReminderListItem[]>({
    queryKey: queryKeys.reminders,
    queryFn: async () => {
      const { data } = await listReminders();
      return data ?? [];
    },
  });
}
