import { describe, expect, it } from "vitest";
import { settingsEndpoint, settingsSegment } from "./settings-endpoint";
import type { UiContribution } from "./types";

const entry: UiContribution = {
  id: "ze_news.settings",
  plugin: "ze_news",
  kind: "settings_section",
  label: "News",
  icon: "newspaper",
  path: "news",
  settings_operation_id: "getNewsSettings",
  priority: 100,
  show_in_mobile_nav: true,
};

describe("settingsEndpoint", () => {
  it("uses explicit path segment", () => {
    expect(settingsEndpoint(entry)).toBe("/api/v0/news/settings");
  });

  it("derives segment from plugin name when path is missing", () => {
    expect(settingsSegment({ ...entry, path: null })).toBe("news");
  });
});
