import { useQueryClient } from "@tanstack/react-query";
import { useFrame } from "@/shared/api";
import { refreshKeysForScreen } from "@/shared/lib";

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
