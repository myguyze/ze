import { describe, it, expect } from "vitest";
import { refreshKeysForScreen } from "@/shared/lib/query-keys";

const manifest = {
  nav: [
    {
      id: "ze_news.overview",
      plugin: "ze_news",
      kind: "nav" as const,
      label: "News",
      icon: "newspaper",
      path: "news",
      page_operation_id: "getNewsPage",
      show_in_mobile_nav: true,
      priority: 100,
    },
    {
      id: "ze_personal.contacts.overview",
      plugin: "ze_personal",
      kind: "nav" as const,
      label: "Contacts",
      icon: "users",
      path: "contacts",
      page_operation_id: "getContactsPage",
      show_in_mobile_nav: true,
      priority: 100,
    },
  ],
  settings_sections: [],
};

describe("refreshKeysForScreen", () => {
  it("returns query keys for core-owned screens", () => {
    expect(refreshKeysForScreen("goals")).toEqual(["goals"]);
    expect(refreshKeysForScreen("costs")).toEqual(["costs"]);
  });

  it("resolves plugin screens from manifest nav path", () => {
    expect(refreshKeysForScreen("news", manifest)).toEqual([
      "plugin-page",
      "ze_news.overview",
    ]);
    expect(refreshKeysForScreen("contacts", manifest)).toEqual([
      "plugin-page",
      "ze_personal.contacts.overview",
    ]);
  });

  it("returns undefined for unknown screens", () => {
    expect(refreshKeysForScreen("chat")).toBeUndefined();
    expect(refreshKeysForScreen("news")).toBeUndefined();
    expect(refreshKeysForScreen("")).toBeUndefined();
  });
});
