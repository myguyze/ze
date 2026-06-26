import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/shared/lib";
import { fetchUiManifest } from "./fetchUiManifest";

export function useUiManifestQuery() {
  return useQuery({
    queryKey: queryKeys.uiManifest,
    queryFn: fetchUiManifest,
    staleTime: 5 * 60_000,
  });
}
