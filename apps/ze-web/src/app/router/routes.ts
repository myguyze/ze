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
  reminders: () => import("@/pages/reminders").then((m) => ({ default: m.RemindersPage })),
  contacts: () => import("@/pages/contacts").then((m) => ({ default: m.ContactsPage })),
  costs: () => import("@/pages/costs").then((m) => ({ default: m.CostsPage })),
  news: () => import("@/pages/news").then((m) => ({ default: m.NewsPage })),
  settings: () => import("@/pages/settings").then((m) => ({ default: m.SettingsPage })),
};

export const appRoutes: RouteMeta[] = navRoutes.map((meta) => ({
  ...meta,
  lazy: lazyByPath[meta.path === "/" ? "/" : meta.path],
}));

export const settingsRoute: RouteMeta = {
  ...settingsNavRoute,
  lazy: lazyByPath.settings,
};
