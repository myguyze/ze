import type { LucideIcon } from "lucide-react";
import {
  MessageCircle,
  Target,
  Workflow,
  BarChart2,
  Brain,
  Activity,
  Network,
  Settings,
} from "lucide-react";

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
  { path: "brain-activity", label: "Activity", icon: Activity, showInMobileNav: false },
  { path: "brain-graph", label: "Graph", icon: Network, showInMobileNav: false },
];

export const settingsNavRoute: NavRouteMeta = {
  path: "settings",
  label: "Settings",
  icon: Settings,
  showInMobileNav: true,
};

export const mobileNavRoutes = [
  ...navRoutes.filter((r) => r.showInMobileNav),
  settingsNavRoute,
];
