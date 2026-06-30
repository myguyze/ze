import { loadPluginSettings, type UiContributionSchema } from "@myguyze/ze-client";

export async function fetchPluginSettings(entry: UiContributionSchema) {
  return loadPluginSettings(entry);
}
