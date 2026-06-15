import { useQueryClient } from "@tanstack/react-query";
import { useFrame } from "@/features/websocket/useWebSocket";
import { refreshKeysForScreen } from "@/lib/queryKeys";

export function RefreshHandler() {
  const queryClient = useQueryClient();

  useFrame("refresh", (frame) => {
    const keys = refreshKeysForScreen(frame.screen);
    if (keys) {
      void queryClient.invalidateQueries({ queryKey: [...keys] });
    }
  });

  return null;
}
