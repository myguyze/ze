import type { PluginPageResponse, UiContributionSchema } from "./generated";
import { loadPluginOperation } from "./sdk-dispatch";

export async function loadPluginPage(entry: UiContributionSchema): Promise<PluginPageResponse> {
  const operationId = entry.page_operation_id;
  if (!operationId) {
    throw new Error(`Unsupported plugin page operation: ${operationId ?? "missing"}`);
  }
  return loadPluginOperation(operationId);
}

export async function loadPluginSettings(entry: UiContributionSchema): Promise<PluginPageResponse> {
  const operationId = entry.settings_operation_id;
  if (!operationId) {
    throw new Error(`Unsupported plugin settings operation: ${operationId ?? "missing"}`);
  }
  return loadPluginOperation(operationId);
}
