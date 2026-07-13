import { useInfiniteQuery } from "@tanstack/react-query";
import { listNotifications } from "@myguyze/ze-client";
import type { NotificationListResponse } from "@myguyze/ze-client";
import { queryKeys } from "@/shared/lib";

export function useNotificationsQuery(options?: { unreadOnly?: boolean; markRead?: boolean }) {
  const unreadOnly = options?.unreadOnly ?? false;
  const markRead = options?.markRead ?? false;

  return useInfiniteQuery({
    queryKey: queryKeys.notifications(unreadOnly),
    queryFn: async ({ pageParam }) => {
      const { data } = await listNotifications({
        query: {
          limit: 20,
          cursor: pageParam ?? undefined,
          unread_only: unreadOnly,
          mark_read: pageParam == null ? markRead : false,
        },
      });
      return data as NotificationListResponse;
    },
    getNextPageParam: (lastPage) => lastPage?.next_cursor ?? undefined,
    initialPageParam: undefined as string | undefined,
  });
}
