import { describe, expect, it } from "vitest";
import { Target } from "lucide-react";
import type { NavRouteMeta } from "@/shared/config";
import { mergeNavRoutes } from "./merge-nav-routes";
import type { UiContribution } from "./types";

const coreRoutes: NavRouteMeta[] = [
  { path: "/", label: "Chat", icon: Target, index: true },
  { path: "news", label: "News", icon: Target },
];

const financeNav: UiContribution = {
  id: "ze_finance.overview",
  plugin: "ze_finance",
  kind: "nav",
  label: "Finance",
  icon: "landmark",
  path: "finance",
  priority: 10,
  show_in_mobile_nav: true,
};

describe("mergeNavRoutes", () => {
  it("appends plugin routes after core routes", () => {
    const merged = mergeNavRoutes(coreRoutes, [financeNav]);
    expect(merged.map((route) => route.path)).toEqual(["/", "news", "finance"]);
    expect(merged[2]?.label).toBe("Finance");
  });

  it("skips plugin routes that collide with core paths", () => {
    const duplicate: UiContribution = { ...financeNav, path: "news", label: "Other News" };
    const merged = mergeNavRoutes(coreRoutes, [duplicate]);
    expect(merged.map((route) => route.path)).toEqual(["/", "news"]);
    expect(merged[1]?.label).toBe("News");
  });
});
