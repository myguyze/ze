import { useQueryClient } from "@tanstack/react-query";
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

  return null;
}
