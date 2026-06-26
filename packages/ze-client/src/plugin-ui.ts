import {
  getContactsPage,
  getNewsPage,
  getNewsSettings,
  getRemindersPage,
  type PluginPageResponse,
  type UiContributionSchema,
} from "./generated";

type PageLoader = () => Promise<PluginPageResponse>;

const PAGE_LOADERS: Record<string, PageLoader> = {
  getContactsPage: async () => {
    const { data, error } = await getContactsPage();
    if (error || !data) {
      throw new Error("Failed to load plugin page");
    }
    return data;
  },
  getRemindersPage: async () => {
    const { data, error } = await getRemindersPage();
    if (error || !data) {
      throw new Error("Failed to load plugin page");
    }
    return data;
  },
  getNewsPage: async () => {
    const { data, error } = await getNewsPage();
    if (error || !data) {
      throw new Error("Failed to load plugin page");
    }
    return data;
  },
};

const SETTINGS_LOADERS: Record<string, PageLoader> = {
  getNewsSettings: async () => {
    const { data, error } = await getNewsSettings();
    if (error || !data) {
      throw new Error("Failed to load plugin settings");
    }
    return data;
  },
};

export async function loadPluginPage(entry: UiContributionSchema): Promise<PluginPageResponse> {
  const operationId = entry.page_operation_id;
  if (!operationId || !(operationId in PAGE_LOADERS)) {
    throw new Error(`Unsupported plugin page operation: ${operationId ?? "missing"}`);
  }
  return PAGE_LOADERS[operationId]();
}

export async function loadPluginSettings(entry: UiContributionSchema): Promise<PluginPageResponse> {
  const operationId = entry.settings_operation_id;
  if (!operationId || !(operationId in SETTINGS_LOADERS)) {
    throw new Error(`Unsupported plugin settings operation: ${operationId ?? "missing"}`);
  }
  return SETTINGS_LOADERS[operationId]();
}
