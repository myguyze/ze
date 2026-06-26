import type { LucideIcon } from "lucide-react";
import {
  MessageCircle,
  Target,
  Bell,
  Users,
  BarChart2,
  Newspaper,
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
  { path: "reminders", label: "Reminders", icon: Bell, showInMobileNav: true },
  { path: "contacts", label: "Contacts", icon: Users, showInMobileNav: true },
  { path: "costs", label: "Usage", icon: BarChart2, showInMobileNav: true },
  { path: "news", label: "News", icon: Newspaper, showInMobileNav: true },
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
