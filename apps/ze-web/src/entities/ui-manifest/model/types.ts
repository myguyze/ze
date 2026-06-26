export type UiContributionKind = "nav" | "settings_section";

export interface UiContribution {
  id: string;
  plugin: string;
  kind: UiContributionKind;
  label: string;
  icon: string;
  path?: string | null;
  page_operation_id?: string | null;
  settings_operation_id?: string | null;
  priority: number;
  show_in_mobile_nav: boolean;
}

export interface UiManifest {
  nav: UiContribution[];
  settings_sections: UiContribution[];
}

export interface PluginPageResponse {
  title: string;
  tree: unknown;
}
