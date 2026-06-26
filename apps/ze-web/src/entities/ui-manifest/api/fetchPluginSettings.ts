import { loadPluginSettings, type UiContributionSchema } from "@ze/client";

export async function fetchPluginSettings(entry: UiContributionSchema) {
  return loadPluginSettings(entry);
}
