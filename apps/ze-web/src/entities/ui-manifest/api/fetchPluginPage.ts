import { loadPluginPage, type UiContributionSchema } from "@myguyze/ze-client";

export async function fetchPluginPage(entry: UiContributionSchema) {
  return loadPluginPage(entry);
}
