import { useMutation, useQueryClient } from "@tanstack/react-query";
import { markAllNotificationsRead } from "@myguyze/ze-client";
import { queryKeys } from "@/shared/lib";

export function useMarkAllReadMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const { data, error } = await markAllNotificationsRead();
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.unreadNotificationCount });
    },
  });
}
