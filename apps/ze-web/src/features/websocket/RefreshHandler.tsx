import { useQueryClient } from "@tanstack/react-query";
import { useFrame } from "@/features/websocket/useWebSocket";
import { queryKeysForRefreshScreen } from "./refreshQueries";

export function RefreshHandler() {
  const queryClient = useQueryClient();

  useFrame("refresh", (frame) => {
    const keys = queryKeysForRefreshScreen(frame.screen);
    if (keys) {
      void queryClient.invalidateQueries({ queryKey: [...keys] });
    }
  });

  return null;
}
