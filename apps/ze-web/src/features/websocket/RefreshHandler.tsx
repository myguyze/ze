import { useQueryClient } from "@tanstack/react-query";
import { useFrame } from "@/features/websocket/useWebSocket";

const SCREEN_KEY_MAP: Record<string, string[]> = {
  goals:     ["goals"],
  reminders: ["reminders"],
  contacts:  ["contacts"],
  costs:     ["costs"],
  news:      ["news"],
};

export function RefreshHandler() {
  const queryClient = useQueryClient();

  useFrame("refresh", (frame) => {
    const key = SCREEN_KEY_MAP[frame.screen];
    if (key) {
      void queryClient.invalidateQueries({ queryKey: key });
    }
  });

  return null;
}
