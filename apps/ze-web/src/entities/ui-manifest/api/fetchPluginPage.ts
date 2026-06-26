import { loadPluginPage, type UiContributionSchema } from "@ze/client";

export async function fetchPluginPage(entry: UiContributionSchema) {
  return loadPluginPage(entry);
}
