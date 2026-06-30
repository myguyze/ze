import {
  BarChart2,
  Bell,
  Circle,
  Landmark,
  MessageCircle,
  Newspaper,
  Settings,
  Target,
  Users,
  type LucideIcon,
} from "lucide-react";
import * as LucideIcons from "lucide-react";

const KNOWN_ICONS: Record<string, LucideIcon> = {
  barchart2: BarChart2,
  bar_chart2: BarChart2,
  bell: Bell,
  circle: Circle,
  landmark: Landmark,
  messagecircle: MessageCircle,
  message_circle: MessageCircle,
  newspaper: Newspaper,
  settings: Settings,
  target: Target,
  users: Users,
};

function toPascalCase(name: string): string {
  return name
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join("");
}

export function resolveNavIcon(name: string): LucideIcon {
  const normalized = name.trim().toLowerCase();
  if (normalized in KNOWN_ICONS) {
    return KNOWN_ICONS[normalized];
  }

  const pascal = toPascalCase(name);
  const dynamic = (LucideIcons as unknown as Record<string, LucideIcon | undefined>)[pascal];
  return dynamic ?? Circle;
}
