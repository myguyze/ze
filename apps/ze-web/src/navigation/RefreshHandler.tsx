import { useQueryClient } from "@tanstack/react-query";
import { useWebSocket } from "@/ws/useWebSocket";
import { type InboundFrame } from "@/ws/protocol";

const SCREEN_KEY_MAP: Record<string, string[]> = {
  goals:     ["goals"],
  reminders: ["reminders"],
  contacts:  ["contacts"],
  costs:     ["costs"],
  news:      ["news"],
};

export function RefreshHandler() {
  const queryClient = useQueryClient();

  useWebSocket((frame: InboundFrame) => {
    if (frame.type !== "refresh") return;
    const key = SCREEN_KEY_MAP[frame.screen];
    if (key) {
      void queryClient.invalidateQueries({ queryKey: key });
    }
  });

  return null;
}
