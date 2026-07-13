import { useMutation, useQueryClient } from "@tanstack/react-query";
import { markNotificationRead } from "@myguyze/ze-client";
import { queryKeys } from "@/shared/lib";

export function useMarkReadMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (notificationId: string) => {
      const { error } = await markNotificationRead({ path: { notification_id: notificationId } });
      if (error) throw error;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.unreadNotificationCount });
    },
  });
}
