import type { ComponentType } from "react";
import {
  navRoutes,
  settingsNavRoute,
  type NavRouteMeta,
} from "@/shared/config";

export interface RouteMeta extends NavRouteMeta {
  lazy: () => Promise<{ default: ComponentType }>;
}

const lazyByPath: Record<string, RouteMeta["lazy"]> = {
  "/": () => import("@/pages/chat").then((m) => ({ default: m.ChatPage })),
  goals: () => import("@/pages/goals").then((m) => ({ default: m.GoalsPage })),
  workflows: () => import("@/pages/workflows").then((m) => ({ default: m.WorkflowsPage })),
  costs: () => import("@/pages/costs").then((m) => ({ default: m.CostsPage })),
  "brain-memory": () => import("@/pages/brain-memory").then((m) => ({ default: m.BrainMemoryPage })),
  "brain-graph": () => import("@/pages/brain-graph").then((m) => ({ default: m.BrainGraphPage })),
  data: () => import("@/pages/data").then((m) => ({ default: m.DataPage })),
  settings: () => import("@/pages/settings").then((m) => ({ default: m.SettingsPage })),
  plugin: () => import("@/pages/plugin-page").then((m) => ({ default: m.PluginPage })),
};

export const appRoutes: RouteMeta[] = navRoutes.map((meta) => ({
  ...meta,
  lazy: lazyByPath[meta.path === "/" ? "/" : meta.path],
}));

export const settingsRoute: RouteMeta = {
  ...settingsNavRoute,
  lazy: lazyByPath.settings,
};
