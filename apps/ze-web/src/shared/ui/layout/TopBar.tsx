import { Bell } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import { navRoutes, settingsNavRoute } from "@/shared/config";
import { useBreadcrumb } from "@/shared/lib/breadcrumb";

const allRoutes = [...navRoutes, settingsNavRoute];

function getCurrentRoute(pathname: string) {
  if (pathname === "/") return navRoutes.find((r) => r.index) ?? null;
  const segment = pathname.replace(/^\//, "").split("/")[0];
  return allRoutes.find((r) => r.path === segment) ?? null;
}

const DETAIL_ROUTES: Record<string, { label: string; path: string }> = {
  goals: { label: "Goals", path: "/goals" },
  workflows: { label: "Workflows", path: "/workflows" },
};

function parseDetailRoute(pathname: string) {
  const match = pathname.match(/^\/(goals|workflows)\/[^/]+/);
  if (!match) return null;
  const parent = DETAIL_ROUTES[match[1]];
  const parentRoute = allRoutes.find((r) => r.path === match[1]);
  return parent ? { ...parent, Icon: parentRoute?.icon ?? null } : null;
}

export function TopBar() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { detailTitle } = useBreadcrumb();

  const detail = parseDetailRoute(pathname);
  const currentRoute = detail ? null : getCurrentRoute(pathname);
  const CurrentIcon = currentRoute?.icon ?? null;

  return (
    <div className="flex items-center justify-between px-6 h-14 border-b border-white/[0.08] bg-white/[0.02] flex-shrink-0">
      {/* Left: title / breadcrumb */}
      <div className="flex items-center gap-2.5 min-w-0">
        {detail ? (
          <>
            <button
              onClick={() => navigate(detail.path)}
              className="flex items-center gap-2 text-smoke hover:text-white transition-colors shrink-0"
            >
              {detail.Icon && <detail.Icon className="w-4 h-4" />}
              <span className="text-sm">{detail.label}</span>
            </button>
            <span className="text-white/20 select-none">/</span>
            <span className="text-base font-semibold text-white truncate">
              {detailTitle ?? "…"}
            </span>
          </>
        ) : (
          <div className="flex items-center gap-2.5">
            {CurrentIcon && (
              <CurrentIcon className="w-5 h-5 text-plum-voltage shrink-0" />
            )}
            <span className="text-base font-semibold text-white">
              {currentRoute?.label ?? ""}
            </span>
          </div>
        )}
      </div>

      {/* Right: actions */}
      <div className="flex items-center gap-1 shrink-0">
        <button
          className="flex items-center justify-center w-9 h-9 rounded-pill text-smoke hover:text-white hover:bg-white/5 transition-colors"
          aria-label="Notifications"
        >
          <Bell className="w-[18px] h-[18px]" />
        </button>
      </div>
    </div>
  );
}
