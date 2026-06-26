import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/shared/lib";
import { fetchPluginPage } from "./fetchPluginPage";

export function usePluginPageQuery(path: string | undefined) {
  return useQuery({
    queryKey: queryKeys.pluginPage(path ?? ""),
    queryFn: () => fetchPluginPage(path!),
    enabled: Boolean(path),
    staleTime: 60_000,
  });
}
