import type { LucideIcon } from "lucide-react";
import type { NavRouteMeta } from "@/shared/config";
import { resolveNavIcon } from "@/shared/ui/icons";
import type { UiContribution } from "../model/types";

export function pluginNavRoutes(contributions: UiContribution[]): NavRouteMeta[] {
  return contributions
    .filter((item) => item.kind === "nav" && item.path)
    .map((item) => ({
      path: item.path!,
      label: item.label,
      icon: resolveNavIcon(item.icon),
      showInMobileNav: item.show_in_mobile_nav,
    }));
}

export function mergeNavRoutes(
  coreRoutes: NavRouteMeta[],
  pluginContributions: UiContribution[] = [],
): NavRouteMeta[] {
  const corePaths = new Set(coreRoutes.map((route) => route.path));
  const pluginRoutes = pluginNavRoutes(pluginContributions).filter(
    (route) => !corePaths.has(route.path),
  );
  return [...coreRoutes, ...pluginRoutes];
}

export function mergeMobileNavRoutes(
  coreRoutes: NavRouteMeta[],
  settingsRoute: NavRouteMeta,
  pluginContributions: UiContribution[] = [],
): NavRouteMeta[] {
  const merged = mergeNavRoutes(coreRoutes, pluginContributions);
  return [...merged.filter((route) => route.showInMobileNav), settingsRoute];
}
