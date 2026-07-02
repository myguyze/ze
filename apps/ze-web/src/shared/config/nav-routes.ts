import type { LucideIcon } from "lucide-react";
import {
  MessageCircle,
  Target,
  Workflow,
  BarChart2,
  Library,
  Brain,
  Network,
  Database,
  Server,
  Briefcase,
  Settings,
} from "lucide-react";
import { redirectHintPath } from "@/shared/lib/redirect-hint";

export interface NavRouteMeta {
  path: string;
  label: string;
  icon: LucideIcon;
  index?: boolean;
  showInMobileNav?: boolean;
}

export const navRoutes: NavRouteMeta[] = [
  // Core-owned routes — plugin nav from GET /api/v0/ui/manifest is merged at runtime.
  { path: "/", label: "Chat", icon: MessageCircle, index: true, showInMobileNav: true },
  { path: "goals", label: "Goals", icon: Target, showInMobileNav: true },
  { path: "workflows", label: "Workflows", icon: Workflow, showInMobileNav: true },
  { path: "costs", label: "Usage", icon: BarChart2, showInMobileNav: true },
  { path: "brain-memory", label: "Memory", icon: Brain, showInMobileNav: false },
  { path: "brain-graph", label: "Graph", icon: Network, showInMobileNav: false },
  { path: "data", label: "Data", icon: Database, showInMobileNav: false },
];

/** Work sub-routes — rendered inside the collapsible Work group. */
export const workNavRoutes: NavRouteMeta[] = navRoutes.filter(
  (r) => r.path === "goals" || r.path === "workflows",
);

/** Knowledge sub-routes — rendered inside the collapsible Knowledge group. */
export const knowledgeNavRoutes: NavRouteMeta[] = navRoutes.filter(
  (r) => r.path === "brain-memory" || r.path === "brain-graph",
);

/** System sub-routes — rendered inside the collapsible System group. */
export const systemNavRoutes: NavRouteMeta[] = navRoutes.filter(
  (r) => r.path === "costs" || r.path === "data",
);

export { Library as KnowledgeIcon, Server as SystemIcon, Briefcase as WorkIcon };

export const settingsNavRoute: NavRouteMeta = {
  path: "settings",
  label: "Settings",
  icon: Settings,
  showInMobileNav: true,
};

/** Hash target for export/import/delete in SettingsWorkspace. */
export const settingsDataSectionId = "your-data";

export function settingsDataPath(): string {
  return redirectHintPath(`/${settingsNavRoute.path}`, settingsDataSectionId);
}

export const mobileNavRoutes = [
  ...navRoutes.filter((r) => r.showInMobileNav),
  settingsNavRoute,
];
