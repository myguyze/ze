import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/shared/lib";
import type { UiContribution } from "../model/types";
import { fetchPluginPage } from "./fetchPluginPage";

export function usePluginPageQuery(entry: UiContribution | undefined) {
  return useQuery({
    queryKey: queryKeys.pluginPage(entry?.id ?? ""),
    queryFn: () => fetchPluginPage(entry!),
    enabled: entry != null,
    staleTime: 60_000,
  });
}
