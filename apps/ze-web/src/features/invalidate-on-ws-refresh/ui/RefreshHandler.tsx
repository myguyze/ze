import type { InfiniteData } from "@tanstack/react-query";
import { useQueryClient } from "@tanstack/react-query";
import type { NotificationListResponse } from "@myguyze/ze-client";
import type { UiManifest } from "@/entities/ui-manifest";
import { useFrame } from "@/shared/api";
import { queryKeys, refreshKeysForScreen } from "@/shared/lib";

export function RefreshHandler() {
  const queryClient = useQueryClient();

  useFrame("refresh", (frame) => {
    const manifest = queryClient.getQueryData<UiManifest>(queryKeys.uiManifest);
    const keys = refreshKeysForScreen(frame.screen, manifest);
    if (keys) {
      void queryClient.invalidateQueries({ queryKey: [...keys] });
    }
  });

  useFrame("notification", (frame) => {
    queryClient.setQueriesData<InfiniteData<NotificationListResponse>>(
      { queryKey: ["notifications"] },
      (data) => {
        if (!data) return data;
        const [firstPage, ...rest] = data.pages;
        const item = {
          id: frame.id,
          event_type: frame.event_type,
          source: frame.source,
          title: frame.title,
          body: frame.body,
          target_type: frame.target_type,
          target_id: frame.target_id,
          created_at: frame.created_at,
          read: false,
        };
        const updatedFirstPage: NotificationListResponse = firstPage
          ? { ...firstPage, items: [item, ...firstPage.items] }
          : { items: [item], next_cursor: null };
        return { ...data, pages: [updatedFirstPage, ...rest] };
      },
    );

    queryClient.setQueryData<number>(
      queryKeys.unreadNotificationCount,
      (count) => (count ?? 0) + 1,
    );
  });

  return null;
}
