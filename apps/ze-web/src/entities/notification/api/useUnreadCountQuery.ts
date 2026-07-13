import { useQuery } from "@tanstack/react-query";
import { getUnreadNotificationCount } from "@myguyze/ze-client";
import { queryKeys } from "@/shared/lib";

export function useUnreadCountQuery() {
  return useQuery<number>({
    queryKey: queryKeys.unreadNotificationCount,
    queryFn: async () => {
      const { data, error } = await getUnreadNotificationCount();
      if (error) throw error;
      return data!.count;
    },
  });
}
