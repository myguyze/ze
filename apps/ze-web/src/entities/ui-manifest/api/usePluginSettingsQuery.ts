import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/shared/lib";
import type { UiContribution } from "../model/types";
import { fetchPluginSettings } from "./fetchPluginSettings";

export function usePluginSettingsQuery(entry: UiContribution, enabled = true) {
  return useQuery({
    queryKey: queryKeys.pluginSettings(entry.id),
    queryFn: () => fetchPluginSettings(entry),
    enabled,
    staleTime: 60_000,
  });
}
